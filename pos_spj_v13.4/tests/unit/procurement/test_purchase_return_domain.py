"""PurchaseReturn domain entity — status transitions (mirrors test_procurement_domain.py)."""

from decimal import Decimal

import pytest

from backend.domain.procurement.entities import PurchaseReturn, PurchaseReturnLine
from backend.domain.procurement.enums import PurchaseReturnReason, PurchaseReturnStatus
from backend.domain.procurement.exceptions import (
    InvalidPurchaseStateError,
    ProcurementDomainError,
)
from backend.domain.procurement.value_objects import DocumentNumber, Money


def _return(**kwargs):
    return PurchaseReturn.create(
        DocumentNumber("DEV", 2026, 1), "sup-1", "br-1", "wh-1",
        PurchaseReturnReason.DAMAGED, created_by_user_id="u1", **kwargs)


class TestPurchaseReturnLine:
    def test_create_requires_positive_quantity(self):
        with pytest.raises(ProcurementDomainError):
            PurchaseReturnLine.create("p1", 0)
        with pytest.raises(ProcurementDomainError):
            PurchaseReturnLine.create("p1", -1)

    def test_create_rejects_float(self):
        with pytest.raises(ProcurementDomainError):
            PurchaseReturnLine.create("p1", 1.5)

    def test_create_defaults(self):
        line = PurchaseReturnLine.create("p1", 3)
        assert line.quantity == Decimal("3")
        assert line.unit_cost is None
        assert line.lot is None
        assert line.notes == ""


class TestPurchaseReturn:
    def test_create_defaults_to_draft(self):
        pr = _return()
        assert pr.status is PurchaseReturnStatus.DRAFT
        assert pr.reason is PurchaseReturnReason.DAMAGED
        assert pr.lines == []
        assert pr.confirmed_at is None

    def test_references_original_receipt_without_deleting_it(self):
        pr = _return(goods_receipt_id="gr-1", purchase_order_id="po-1")
        assert pr.goods_receipt_id == "gr-1"
        assert pr.purchase_order_id == "po-1"

    def test_add_line_in_draft(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 2, unit_cost=Money(Decimal("10"))))
        assert len(pr.lines) == 1
        assert pr.total_quantity() == Decimal("2")

    def test_confirm_requires_at_least_one_line(self):
        pr = _return()
        with pytest.raises(InvalidPurchaseStateError):
            pr.confirm()

    def test_confirm_transitions_to_confirmed(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 5))
        pr.confirm()
        assert pr.status is PurchaseReturnStatus.CONFIRMED
        assert pr.confirmed_at is not None

    def test_cannot_add_line_after_confirm(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 1))
        pr.confirm()
        with pytest.raises(InvalidPurchaseStateError):
            pr.add_line(PurchaseReturnLine.create("p2", 1))

    def test_cannot_confirm_twice(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 1))
        pr.confirm()
        with pytest.raises(InvalidPurchaseStateError):
            pr.confirm()

    def test_cancel_draft(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 1))
        pr.cancel()
        assert pr.status is PurchaseReturnStatus.CANCELLED

    def test_cannot_cancel_confirmed_return(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 1))
        pr.confirm()
        with pytest.raises(InvalidPurchaseStateError):
            pr.cancel()

    def test_cannot_cancel_twice(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 1))
        pr.cancel()
        with pytest.raises(InvalidPurchaseStateError):
            pr.cancel()

    def test_total_quantity_sums_lines(self):
        pr = _return()
        pr.add_line(PurchaseReturnLine.create("p1", 2))
        pr.add_line(PurchaseReturnLine.create("p2", 3))
        assert pr.total_quantity() == Decimal("5")
