"""INV-7 — lots + expiration domain tests (entity, FEFO allocation, expiry risk)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.enums import (
    AllocationStrategy,
    ExpiryRisk,
    LotOrigin,
    LotQualityStatus,
)
from backend.domain.inventory.exceptions import (
    InsufficientInventoryError,
    InventoryDomainError,
)
from backend.domain.inventory.services import (
    ExpiryRiskService,
    LotAllocationService,
    LotCandidate,
)

TODAY = date(2026, 7, 18)


def _cand(lot_id, qty, exp=None, received=None, status=LotQualityStatus.RELEASED):
    return LotCandidate(lot_id=lot_id, available_quantity=Decimal(str(qty)),
                        expiration_date=exp, received_at=received, quality_status=status)


class TestLotEntity:
    def test_create_and_traceability_fields(self):
        lot = InventoryLot.create(product_id="p1", lot_code="L-1",
                                  origin_type=LotOrigin.PURCHASE,
                                  supplier_lot_code="SUP-9", expiration_date="2026-08-01")
        assert len(lot.id) == 36 and lot.supplier_lot_code == "SUP-9"
        assert not lot.is_released and lot.is_allocatable

    def test_requires_code(self):
        with pytest.raises(InventoryDomainError):
            InventoryLot.create(product_id="p1", lot_code="", origin_type=LotOrigin.PURCHASE)

    def test_block_and_release(self):
        lot = InventoryLot.create(product_id="p1", lot_code="L-1",
                                  origin_type=LotOrigin.PURCHASE)
        lot.block(status=LotQualityStatus.QUARANTINED)
        assert lot.quality_status is LotQualityStatus.QUARANTINED and not lot.is_allocatable
        lot.release()
        assert lot.is_released

    def test_is_expired(self):
        lot = InventoryLot.create(product_id="p1", lot_code="L-1",
                                  origin_type=LotOrigin.PURCHASE,
                                  expiration_date="2026-07-10")
        assert lot.is_expired(as_of="2026-07-18")
        assert not lot.is_expired(as_of="2026-07-01")


class TestFefoAllocation:
    def setup_method(self):
        self.svc = LotAllocationService()

    def test_fefo_picks_earliest_expiry_first(self):
        cands = [_cand("late", 10, exp="2026-09-01"),
                 _cand("soon", 10, exp="2026-07-25"),
                 _cand("mid", 10, exp="2026-08-10")]
        plan = self.svc.allocate(cands, Decimal("15"),
                                 strategy=AllocationStrategy.FEFO, as_of=TODAY)
        assert plan[0].lot_id == "soon" and plan[0].quantity == Decimal("10")
        assert plan[1].lot_id == "mid" and plan[1].quantity == Decimal("5")

    def test_skips_expired_lots(self):
        cands = [_cand("exp", 10, exp="2026-07-01"),
                 _cand("ok", 10, exp="2026-08-01")]
        plan = self.svc.allocate(cands, Decimal("5"), as_of=TODAY)
        assert len(plan) == 1 and plan[0].lot_id == "ok"

    def test_skips_blocked_lots(self):
        cands = [_cand("blk", 10, exp="2026-07-25", status=LotQualityStatus.BLOCKED),
                 _cand("ok", 10, exp="2026-08-01")]
        plan = self.svc.allocate(cands, Decimal("5"), as_of=TODAY)
        assert plan[0].lot_id == "ok"

    def test_require_released_excludes_pending(self):
        cands = [_cand("pend", 10, exp="2026-07-25",
                       status=LotQualityStatus.PENDING_INSPECTION)]
        with pytest.raises(InsufficientInventoryError):
            self.svc.allocate(cands, Decimal("5"), as_of=TODAY, require_released=True)

    def test_min_shelf_life_filters(self):
        cands = [_cand("short", 10, exp="2026-07-20"),  # 2 days left
                 _cand("long", 10, exp="2026-08-20")]
        plan = self.svc.allocate(cands, Decimal("5"), as_of=TODAY, min_shelf_life_days=7)
        assert plan[0].lot_id == "long"

    def test_insufficient_raises(self):
        with pytest.raises(InsufficientInventoryError):
            self.svc.allocate([_cand("a", 3, exp="2026-08-01")], Decimal("5"), as_of=TODAY)

    def test_fifo_and_lifo_use_received_date(self):
        cands = [_cand("old", 10, received="2026-01-01"),
                 _cand("new", 10, received="2026-06-01")]
        fifo = self.svc.allocate(cands, Decimal("5"), strategy=AllocationStrategy.FIFO,
                                 as_of=TODAY)
        lifo = self.svc.allocate(cands, Decimal("5"), strategy=AllocationStrategy.LIFO,
                                 as_of=TODAY)
        assert fifo[0].lot_id == "old" and lifo[0].lot_id == "new"


class TestExpiryRisk:
    def setup_method(self):
        self.svc = ExpiryRiskService()

    def test_expired(self):
        a = self.svc.classify("2026-07-10", as_of=TODAY)
        assert a.risk is ExpiryRisk.EXPIRED and a.days_to_expiry == -8

    def test_critical(self):
        assert self.svc.classify("2026-07-19", as_of=TODAY, critical_days=2).risk \
            is ExpiryRisk.CRITICAL

    def test_warning(self):
        assert self.svc.classify("2026-07-23", as_of=TODAY, warning_days=7).risk \
            is ExpiryRisk.WARNING

    def test_ok(self):
        assert self.svc.classify("2026-09-01", as_of=TODAY).risk is ExpiryRisk.OK

    def test_no_expiration_is_ok(self):
        a = self.svc.classify(None, as_of=TODAY)
        assert a.risk is ExpiryRisk.OK and a.days_to_expiry is None
