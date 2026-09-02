"""ORD-20 — DriverCashCollection (§44-45): full/partial/failed collection
outcomes, dispute/settlement transitions."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.cash_collection import DriverCashCollection
from backend.domain.orders_delivery.enums import CollectionPaymentMethod, CollectionStatus
from backend.domain.orders_delivery.exceptions import InvalidCashCollectionError
from backend.shared.ids import new_uuid


def _collection(expected: str = "100.00") -> DriverCashCollection:
    return DriverCashCollection.create(
        delivery_job_id=new_uuid(), driver_id=new_uuid(),
        expected_amount=Decimal(expected), payment_method=CollectionPaymentMethod.CASH)


class TestRecordCollection:
    def test_full_collection(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("100.00"))
        assert collection.status == CollectionStatus.COLLECTED

    def test_partial_collection(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("60.00"))
        assert collection.status == CollectionStatus.PARTIALLY_COLLECTED

    def test_zero_collection_is_failed(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("0"))
        assert collection.status == CollectionStatus.FAILED

    def test_overpayment_still_collected(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("150.00"))
        assert collection.status == CollectionStatus.COLLECTED

    def test_can_retry_after_failed(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("0"))
        collection.record_collection(collected_amount=Decimal("100.00"))
        assert collection.status == CollectionStatus.COLLECTED

    def test_cannot_re_record_already_collected(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("100.00"))
        with pytest.raises(InvalidCashCollectionError):
            collection.record_collection(collected_amount=Decimal("100.00"))


class TestSettlementTransitions:
    def test_dispute_requires_collected_status(self):
        collection = _collection()
        with pytest.raises(InvalidCashCollectionError):
            collection.dispute()

    def test_dispute_from_collected(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("100.00"))
        collection.dispute()
        assert collection.status == CollectionStatus.DISPUTED

    def test_full_settlement_flow(self):
        collection = _collection()
        collection.record_collection(collected_amount=Decimal("100.00"))
        collection.mark_pending_settlement()
        assert collection.status == CollectionStatus.PENDING_SETTLEMENT
        collection.mark_settled()
        assert collection.status == CollectionStatus.SETTLED

    def test_cannot_settle_without_pending(self):
        collection = _collection()
        with pytest.raises(InvalidCashCollectionError):
            collection.mark_settled()
