# tests/test_order_draft_entity.py — WA-10
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.whatsapp.entities.order_draft import (
    EmptyOrderDraftError,
    OrderDraft,
    OrderDraftAlreadyFinalizedError,
    OrderDraftLine,
)
from domain.whatsapp.enums import DeliveryMethod, OrderDraftStatus


def _draft() -> OrderDraft:
    return OrderDraft.start(conversation_id="conv-1", branch_id="branch-1")


class TestOrderDraftLine:
    def test_subtotal(self):
        line = OrderDraftLine.create(
            product_external_id="p1", product_name="Bistec", quantity=2.5, unit="kg", unit_price=180.0
        )
        assert line.subtotal == 450.0

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(ValueError):
            OrderDraftLine.create(product_external_id="p1", product_name="Bistec", quantity=0, unit="kg", unit_price=180.0)


class TestOrderDraftStart:
    def test_starts_building_with_no_lines(self):
        draft = _draft()
        assert draft.status == OrderDraftStatus.BUILDING
        assert draft.lines == []
        assert draft.total == 0

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7

        assert is_uuidv7(_draft().id)

    def test_requires_conversation_id(self):
        with pytest.raises(ValueError):
            OrderDraft.start(conversation_id="")


class TestOrderDraftLines:
    def test_add_line_updates_total(self):
        draft = _draft()
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        draft.add_line(product_external_id="p2", product_name="Costilla", quantity=1, unit="kg", unit_price=120.0)
        assert draft.total == 480.0

    def test_remove_line(self):
        draft = _draft()
        line = draft.add_line(product_external_id="p1", product_name="Bistec", quantity=2, unit="kg", unit_price=180.0)
        draft.remove_line(line.id)
        assert draft.lines == []
        assert draft.total == 0

    def test_cannot_edit_after_confirm(self):
        draft = _draft()
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        draft.confirm()
        with pytest.raises(OrderDraftAlreadyFinalizedError):
            draft.add_line(product_external_id="p2", product_name="Costilla", quantity=1, unit="kg", unit_price=100.0)

    def test_cannot_edit_after_cancel(self):
        draft = _draft()
        draft.cancel()
        with pytest.raises(OrderDraftAlreadyFinalizedError):
            draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)


class TestOrderDraftDeliveryAndCustomer:
    def test_set_delivery_method(self):
        draft = _draft()
        draft.set_delivery_method(DeliveryMethod.DELIVERY)
        assert draft.delivery_method == DeliveryMethod.DELIVERY

    def test_set_customer(self):
        draft = _draft()
        draft.set_customer("cust-1")
        assert draft.customer_external_id == "cust-1"


class TestOrderDraftConfirmation:
    def test_confirm_requires_at_least_one_line(self):
        draft = _draft()
        with pytest.raises(EmptyOrderDraftError):
            draft.confirm()

    def test_request_confirmation_requires_lines(self):
        draft = _draft()
        with pytest.raises(EmptyOrderDraftError):
            draft.request_confirmation()

    def test_request_confirmation_then_confirm(self):
        draft = _draft()
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        draft.request_confirmation()
        assert draft.status == OrderDraftStatus.AWAITING_CONFIRMATION
        draft.confirm()
        assert draft.status == OrderDraftStatus.CONFIRMED
        assert draft.is_terminal() is True

    def test_confirm_directly_from_building_is_allowed(self):
        draft = _draft()
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        draft.confirm()
        assert draft.status == OrderDraftStatus.CONFIRMED

    def test_cannot_confirm_twice(self):
        draft = _draft()
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        draft.confirm()
        with pytest.raises(OrderDraftAlreadyFinalizedError):
            draft.confirm()

    def test_cannot_cancel_a_confirmed_draft(self):
        draft = _draft()
        draft.add_line(product_external_id="p1", product_name="Bistec", quantity=1, unit="kg", unit_price=100.0)
        draft.confirm()
        with pytest.raises(OrderDraftAlreadyFinalizedError):
            draft.cancel()


# ── Dinero en Decimal (§9): estas pruebas fallarían con la implementación float ──

def test_subtotal_uses_commercial_rounding_not_binary_float():
    """Con float, `round(1 * 2.675, 2)` da 2.67 y el cobro pierde un centavo.

    No es un detalle teórico: 2.675 no es representable en binario, se almacena
    como 2.67499999999999982236431605997495353221893310546875, y `round()`
    redondea hacia abajo. Decimal + ROUND_HALF_UP da 2.68, que es lo que un
    cliente espera ver cobrado.
    """
    line = OrderDraftLine.create(
        product_external_id="P1", product_name="Arrachera",
        quantity=1, unit="kg", unit_price="2.675",
    )
    assert line.subtotal == Decimal("2.68")
    assert round(1 * 2.675, 2) == 2.67  # lo que hacía la implementación anterior


def test_subtotal_is_exact_for_quantities_that_float_cannot_represent():
    """3 x 0.145 = 0.435 exacto. En float da 0.43 (un centavo menos)."""
    line = OrderDraftLine.create(
        product_external_id="P2", product_name="Especias",
        quantity="3", unit="kg", unit_price="0.145",
    )
    assert line.subtotal == Decimal("0.44")
    assert round(3 * 0.145, 2) == 0.43  # lo que hacía la implementación anterior


def test_float_input_is_normalised_through_str_not_binary():
    """Un precio que llega como float desde el catálogo del ERP no debe
    arrastrar el error binario a la aritmética posterior."""
    line = OrderDraftLine.create(
        product_external_id="P3", product_name="Chorizo",
        quantity=1, unit="kg", unit_price=0.1,
    )
    assert line.unit_price == Decimal("0.1")
    assert str(line.unit_price) == "0.1"          # no 0.1000000000000000055511151231257827
    assert Decimal(0.1) != Decimal("0.1")          # la conversión insegura que se evita


def test_total_accumulates_in_decimal_without_drift():
    draft = OrderDraft.start(conversation_id="C1")
    for _ in range(10):
        draft.add_line(product_external_id="P", product_name="Bistec",
                       quantity=1, unit="kg", unit_price="0.1")
    assert draft.total == Decimal("1.00")
    assert isinstance(draft.total, Decimal)


def test_money_fields_are_decimal_never_float():
    line = OrderDraftLine.create(
        product_external_id="P4", product_name="Costilla",
        quantity=2, unit="kg", unit_price=150.5,
    )
    assert isinstance(line.quantity, Decimal)
    assert isinstance(line.unit_price, Decimal)
    assert isinstance(line.subtotal, Decimal)
    assert not isinstance(line.unit_price, float)
