# tests/test_business_operation_entity.py — WA-10
from __future__ import annotations

import pytest

from domain.whatsapp.entities.business_operation import (
    BusinessOperationIdempotencyRecord,
    IdempotencyRecordAlreadyFinalizedError,
)
from domain.whatsapp.enums import IdempotencyStatus


def _record() -> BusinessOperationIdempotencyRecord:
    return BusinessOperationIdempotencyRecord.start(
        operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT", aggregate_id="draft-1", fingerprint="fp-1"
    )


class TestStart:
    def test_starts_pending(self):
        assert _record().status == IdempotencyStatus.PENDING

    def test_id_and_operation_id_are_both_valid_uuidv7_and_distinct(self):
        from backend.shared.ids import is_uuidv7

        record = _record()
        assert is_uuidv7(record.id)
        assert is_uuidv7(record.operation_id)
        assert record.id != record.operation_id

    def test_requires_fingerprint(self):
        with pytest.raises(ValueError):
            BusinessOperationIdempotencyRecord.start(
                operation_type="CREATE_ORDER", aggregate_type="ORDER_DRAFT", aggregate_id="d1", fingerprint=""
            )


class TestComplete:
    def test_complete_sets_result_and_timestamp(self):
        record = _record()
        record.complete("order-1")
        assert record.status == IdempotencyStatus.COMPLETED
        assert record.result_reference == "order-1"
        assert record.completed_at is not None

    def test_cannot_complete_twice(self):
        record = _record()
        record.complete("order-1")
        with pytest.raises(IdempotencyRecordAlreadyFinalizedError):
            record.complete("order-2")

    def test_cannot_fail_after_complete(self):
        record = _record()
        record.complete("order-1")
        with pytest.raises(IdempotencyRecordAlreadyFinalizedError):
            record.fail()


class TestFail:
    def test_fail_sets_status_and_timestamp(self):
        record = _record()
        record.fail()
        assert record.status == IdempotencyStatus.FAILED
        assert record.completed_at is not None
        assert record.result_reference is None
