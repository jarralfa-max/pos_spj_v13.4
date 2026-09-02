"""ORD-21 — DriverSettlement (§46): reconciliation, BALANCED vs
WITH_DIFFERENCE auto-resolution, review/approve/post/close lifecycle."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.cash_collection import DriverCashCollection
from backend.domain.orders_delivery.enums import CollectionPaymentMethod, SettlementStatus
from backend.domain.orders_delivery.exceptions import (
    InvalidSettlementStateError,
    SettlementRequiresCollectionsError,
)
from backend.domain.orders_delivery.settlement import DriverSettlement
from backend.shared.ids import new_uuid


def _collection(expected: str, collected: str) -> DriverCashCollection:
    c = DriverCashCollection.create(
        delivery_job_id=new_uuid(), driver_id=new_uuid(),
        expected_amount=Decimal(expected), payment_method=CollectionPaymentMethod.CASH)
    c.record_collection(collected_amount=Decimal(collected))
    return c


class TestDriverSettlementCreation:
    def test_requires_at_least_one_collection(self):
        with pytest.raises(SettlementRequiresCollectionsError):
            DriverSettlement.create(driver_id=new_uuid(), branch_id=new_uuid(), collections=[])

    def test_balanced_when_totals_match(self):
        collections = [_collection("100", "100"), _collection("50", "50")]
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=collections)
        assert settlement.status == SettlementStatus.BALANCED
        assert settlement.difference == Decimal("0")
        assert settlement.expected_total == Decimal("150")

    def test_with_difference_when_totals_mismatch(self):
        collections = [_collection("100", "80")]
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=collections)
        assert settlement.status == SettlementStatus.WITH_DIFFERENCE
        assert settlement.difference == Decimal("-20")

    def test_collection_ids_recorded(self):
        collections = [_collection("100", "100")]
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=collections)
        assert settlement.collection_ids == (collections[0].id,)


class TestSettlementLifecycle:
    def test_balanced_can_approve_directly(self):
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=[_collection("100", "100")])
        settlement.approve(approved_by_user_id=new_uuid())
        assert settlement.status == SettlementStatus.APPROVED

    def test_with_difference_requires_review_first(self):
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=[_collection("100", "80")])
        with pytest.raises(InvalidSettlementStateError):
            settlement.approve(approved_by_user_id=new_uuid())
        settlement.submit_for_review(reviewed_by_user_id=new_uuid())
        settlement.approve(approved_by_user_id=new_uuid())
        assert settlement.status == SettlementStatus.APPROVED

    def test_full_lifecycle_to_closed(self):
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=[_collection("100", "100")])
        settlement.approve(approved_by_user_id=new_uuid())
        settlement.post()
        settlement.close()
        assert settlement.status == SettlementStatus.CLOSED
        assert settlement.closed_at is not None

    def test_cannot_transition_closed_settlement(self):
        settlement = DriverSettlement.create(
            driver_id=new_uuid(), branch_id=new_uuid(), collections=[_collection("100", "100")])
        settlement.approve(approved_by_user_id=new_uuid())
        settlement.post()
        settlement.close()
        with pytest.raises(InvalidSettlementStateError):
            settlement.approve(approved_by_user_id=new_uuid())
