# tests/test_inbox_job_entity.py — WA-6
from __future__ import annotations

import pytest

from domain.whatsapp.entities.inbox_job import InboundMessageJob
from domain.whatsapp.enums import InboxStatus
from domain.whatsapp.exceptions import InvalidInboxJobTransitionError


def _job() -> InboundMessageJob:
    return InboundMessageJob.create(message_id="msg-1")


class TestCreate:
    def test_starts_pending(self):
        assert _job().status == InboxStatus.PENDING

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7

        assert is_uuidv7(_job().id)

    def test_requires_message_id(self):
        with pytest.raises(ValueError):
            InboundMessageJob.create(message_id="")

    def test_attempts_start_at_zero(self):
        assert _job().attempts == 0


class TestTransitions:
    def test_claim_moves_to_processing_and_bumps_attempts(self):
        job = _job()
        job.claim()
        assert job.status == InboxStatus.PROCESSING
        assert job.attempts == 1
        assert job.locked_at is not None

    def test_complete_sets_processed_at_and_clears_lock(self):
        job = _job()
        job.claim()
        job.complete()
        assert job.status == InboxStatus.COMPLETED
        assert job.processed_at is not None
        assert job.locked_at is None
        assert job.is_terminal() is True

    def test_fail_records_error(self):
        job = _job()
        job.claim()
        job.fail("boom")
        assert job.status == InboxStatus.FAILED
        assert job.last_error == "boom"

    def test_failed_can_retry(self):
        job = _job()
        job.claim()
        job.fail("boom")
        job.schedule_retry()
        assert job.status == InboxStatus.RETRY

    def test_retry_can_be_claimed_again(self):
        job = _job()
        job.claim()
        job.fail("boom")
        job.schedule_retry()
        job.claim()
        assert job.status == InboxStatus.PROCESSING
        assert job.attempts == 2

    def test_failed_can_go_to_dead_letter(self):
        job = _job()
        job.claim()
        job.fail("boom")
        job.move_to_dead_letter("giving up")
        assert job.status == InboxStatus.DEAD_LETTER
        assert job.last_error == "giving up"
        assert job.is_terminal() is True

    def test_pending_cannot_go_directly_to_completed(self):
        with pytest.raises(InvalidInboxJobTransitionError):
            _job().complete()

    def test_completed_cannot_transition_again(self):
        job = _job()
        job.claim()
        job.complete()
        with pytest.raises(InvalidInboxJobTransitionError):
            job.claim()

    def test_dead_letter_is_final(self):
        job = _job()
        job.claim()
        job.fail("x")
        job.move_to_dead_letter()
        with pytest.raises(InvalidInboxJobTransitionError):
            job.schedule_retry()
