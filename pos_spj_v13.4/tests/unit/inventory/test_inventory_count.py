"""INV-13 — count aggregate: blind capture, lock on confirm, variance, recount."""

from decimal import Decimal

import pytest

from backend.domain.inventory.entities.count import (
    InventoryCount,
    InventoryCountLine,
)
from backend.domain.inventory.enums import CountStatus, CountType
from backend.domain.inventory.exceptions import InventoryDomainError


def _count(expected="10"):
    line = InventoryCountLine.create(product_id="p1", expected_quantity=Decimal(expected),
                                     location_id="loc1")
    c = InventoryCount.create(folio="CNT-1", count_type=CountType.CYCLE_COUNT,
                              branch_id="b1", warehouse_id="w1", lines=[line])
    c.plan(); c.start()
    return c


class TestCountLifecycle:
    def test_blind_count_type_forces_blind(self):
        c = InventoryCount.create(folio="X", count_type=CountType.BLIND_COUNT,
                                  branch_id="b1", warehouse_id="w1",
                                  lines=[InventoryCountLine.create(product_id="p1")],
                                  blind=False)
        assert c.blind is True

    def test_record_then_confirm_computes_variance(self):
        c = _count("10")
        c.record(c.lines[0].id, counted_quantity=Decimal("8"))
        c.confirm()
        assert c.status is CountStatus.COUNTED
        assert c.lines[0].variance_quantity == Decimal("-2") and c.has_variance

    def test_confirm_requires_all_counted(self):
        line2 = InventoryCountLine.create(product_id="p2", expected_quantity=Decimal("5"))
        c = _count("10")
        c.lines.append(line2)
        c.record(c.lines[0].id, counted_quantity=Decimal("10"))
        with pytest.raises(InventoryDomainError):
            c.confirm()  # line2 not counted

    def test_confirmed_count_cannot_be_edited(self):
        c = _count("10")
        c.record(c.lines[0].id, counted_quantity=Decimal("10"))
        c.confirm()
        with pytest.raises(InventoryDomainError):
            c.record(c.lines[0].id, counted_quantity=Decimal("9"))  # locked

    def test_no_variance_when_matches(self):
        c = _count("10")
        c.record(c.lines[0].id, counted_quantity=Decimal("10"))
        c.confirm()
        assert not c.has_variance

    def test_recount_reopens_line(self):
        c = _count("10")
        c.record(c.lines[0].id, counted_quantity=Decimal("8"))
        c.confirm()
        c.request_recount(c.lines[0].id)
        assert c.status is CountStatus.PENDING_RECOUNT
        assert c.lines[0].recount_count == 1 and not c.lines[0].counted
        c.start()  # back to IN_PROGRESS
        c.record(c.lines[0].id, counted_quantity=Decimal("10"))
        c.confirm()
        assert not c.has_variance

    def test_approve(self):
        c = _count("10")
        c.record(c.lines[0].id, counted_quantity=Decimal("10"))
        c.confirm()
        c.approve(user_id="mgr")
        assert c.status is CountStatus.APPROVED and c.approved_by_user_id == "mgr"
