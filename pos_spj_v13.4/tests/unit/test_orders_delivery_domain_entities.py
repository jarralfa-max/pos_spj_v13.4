"""ORD-2 — CustomerOrder/CustomerOrderLine aggregate, lifecycle policy and
OrderTotalsService. Mirrors tests/unit/test_sales_domain_entities.py's
structure where a same-shaped test module exists (Sale/SaleLine)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.enums import (
    FulfillmentType,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
)
from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.exceptions import (
    InvalidOrderQuantityError,
    InvalidOrderStateError,
    OrderCancellationNotAllowedError,
    OrderEmptyError,
    OrderLineNotFoundError,
    OrderNotFoundError,
)
from backend.domain.orders_delivery.policies.order_lifecycle_policy import OrderLifecyclePolicy
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.shared.ids import new_uuid


def _order(**overrides) -> CustomerOrder:
    defaults = dict(
        branch_id=new_uuid(),
        channel=OrderChannel.POS,
        order_type=OrderType.STANDARD,
        fulfillment_type=FulfillmentType.COUNTER,
    )
    defaults.update(overrides)
    return CustomerOrder.create(**defaults)


def _line(order: CustomerOrder, *, qty: str = "2", price: str = "10.00") -> CustomerOrderLine:
    return CustomerOrderLine.create(
        order_id=order.id, product_id=new_uuid(), unit_price=Decimal(price),
        requested_quantity=OrderQuantity(Decimal(qty)),
    )


class TestCustomerOrderCreation:
    def test_create_sets_draft_status(self):
        order = _order()
        assert order.status == OrderStatus.DRAFT
        assert order.lines == []
        assert order.totals.grand_total == Decimal("0")

    def test_line_requires_quantity_or_weight(self):
        order = _order()
        with pytest.raises(InvalidOrderQuantityError):
            CustomerOrderLine.create(order_id=order.id, product_id=new_uuid(),
                                      unit_price=Decimal("10"))


class TestCustomerOrderLines:
    def test_add_line_recalculates_totals(self):
        order = _order()
        order.add_line(_line(order, qty="3", price="10.00"))
        assert order.totals.subtotal == Decimal("30.00")
        assert order.totals.grand_total == Decimal("30.00")

    def test_add_line_rejects_foreign_line(self):
        order = _order()
        other = _order()
        with pytest.raises(OrderNotFoundError):
            order.add_line(_line(other))

    def test_remove_line(self):
        order = _order()
        line = _line(order)
        order.add_line(line)
        order.remove_line(line.id)
        assert order.lines == []
        assert order.totals.grand_total == Decimal("0")

    def test_remove_unknown_line_raises(self):
        order = _order()
        with pytest.raises(OrderLineNotFoundError):
            order.remove_line(new_uuid())

    def test_cannot_add_line_after_confirmation(self):
        order = _order()
        order.add_line(_line(order))
        order.confirm(confirmed_by_user_id=new_uuid())
        with pytest.raises(InvalidOrderStateError):
            order.add_line(_line(order))


class TestCustomerOrderConfirmation:
    def test_confirm_requires_at_least_one_line(self):
        order = _order()
        with pytest.raises(OrderEmptyError):
            order.confirm(confirmed_by_user_id=new_uuid())

    def test_confirm_sets_confirmed_status_and_user(self):
        order = _order()
        order.add_line(_line(order))
        confirmer = new_uuid()
        order.confirm(confirmed_by_user_id=confirmer)
        assert order.status == OrderStatus.CONFIRMED
        assert order.confirmed_by_user_id == confirmer

    def test_double_confirm_raises(self):
        order = _order()
        order.add_line(_line(order))
        order.confirm(confirmed_by_user_id=new_uuid())
        with pytest.raises(InvalidOrderStateError):
            order.confirm(confirmed_by_user_id=new_uuid())


class TestCustomerOrderCancellation:
    def test_cancel_requires_reason(self):
        order = _order()
        with pytest.raises(OrderCancellationNotAllowedError):
            order.cancel(cancelled_by_user_id=new_uuid(), reason="   ")

    def test_cancel_draft_order(self):
        order = _order()
        order.cancel(cancelled_by_user_id=new_uuid(), reason="Cliente canceló")
        assert order.status == OrderStatus.CANCELLED

    def test_cannot_cancel_final_order(self):
        order = _order()
        order.add_line(_line(order))
        order.confirm(confirmed_by_user_id=new_uuid())
        order.move_to_fulfillment()
        order.complete()
        with pytest.raises(OrderCancellationNotAllowedError):
            order.cancel(cancelled_by_user_id=new_uuid(), reason="motivo")


class TestCustomerOrderLifecycle:
    def test_full_happy_path(self):
        order = _order()
        order.add_line(_line(order))
        order.confirm(confirmed_by_user_id=new_uuid())
        order.move_to_fulfillment()
        order.complete()
        assert order.status == OrderStatus.COMPLETED
        order.close()
        assert order.status == OrderStatus.CLOSED

    def test_completed_order_can_be_reversed(self):
        order = _order()
        order.add_line(_line(order))
        order.confirm(confirmed_by_user_id=new_uuid())
        order.move_to_fulfillment()
        order.complete()
        order.reverse()
        assert order.status == OrderStatus.REVERSED

    def test_reversed_order_is_final(self):
        assert OrderStatus.REVERSED in OrderLifecyclePolicy.FINAL_STATUSES


class TestCustomerOrderLineTotals:
    def test_catch_weight_line_prices_on_weight(self):
        order = _order()
        line = CustomerOrderLine.create(
            order_id=order.id, product_id=new_uuid(), unit_price=Decimal("100.00"),
            requested_weight=OrderQuantity(Decimal("2.5"), unit="KG"),
            catch_weight_enabled=True,
        )
        assert line.requested_subtotal == Decimal("250.00")

    def test_final_subtotal_uses_final_weight_after_adjustment(self):
        order = _order()
        line = CustomerOrderLine.create(
            order_id=order.id, product_id=new_uuid(), unit_price=Decimal("100.00"),
            requested_weight=OrderQuantity(Decimal("2.000"), unit="KG"),
            catch_weight_enabled=True,
        )
        line.final_weight = OrderQuantity(Decimal("2.180"), unit="KG")
        assert line.final_subtotal == Decimal("218.000")

    def test_line_status_transition_helper(self):
        order = _order()
        line = _line(order)
        line.mark_status(OrderLineStatus.RESERVED)
        assert line.status == OrderLineStatus.RESERVED
