"""SET-16 — "Idempotencia": sequence_reservation_policy.reserve_with_idempotency.
Pure domain — no DB.
"""

from __future__ import annotations

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.policies.sequence_reservation_policy import reserve_with_idempotency


class TestReserveWithIdempotency:
    def test_no_existing_reservation_advances_the_sequence(self):
        sequence = DocumentNumberSequence.create(prefix="FPR")
        result = reserve_with_idempotency(sequence)
        assert result.sequence_value == 1
        assert sequence.current_value == 1

    def test_existing_reservation_is_returned_unchanged_without_advancing(self):
        sequence = DocumentNumberSequence.create(prefix="FPR")
        first = reserve_with_idempotency(sequence)
        assert sequence.current_value == 1

        replay = reserve_with_idempotency(sequence, existing_reservation=first)
        assert replay is first
        assert sequence.current_value == 1  # unchanged — no second increment

    def test_subsequent_new_operation_still_advances_after_a_replay(self):
        sequence = DocumentNumberSequence.create(prefix="FPR")
        first = reserve_with_idempotency(sequence)
        reserve_with_idempotency(sequence, existing_reservation=first)  # replay, no-op
        second = reserve_with_idempotency(sequence)
        assert second.sequence_value == 2
        assert sequence.current_value == 2
