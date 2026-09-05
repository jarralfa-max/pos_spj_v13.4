# tests/test_outbox_message_entity.py — WA-17
from __future__ import annotations

from datetime import timedelta

import pytest

from domain.whatsapp.entities.outbox_message import (
    MAX_ATTEMPTS,
    OutboxMessage,
    OutboxMessageAlreadyFinalizedError,
)
from domain.whatsapp.enums import OutboxMessageStatus


class TestEnqueueText:
    def test_starts_pending(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        assert message.status == OutboxMessageStatus.PENDING
        assert message.attempts == 0
        assert message.payload == {"kind": "text", "body": "Hola"}

    def test_requires_destination_phone(self):
        with pytest.raises(ValueError):
            OutboxMessage.enqueue_text(destination_phone="", body="Hola")

    def test_requires_non_empty_body(self):
        with pytest.raises(ValueError):
            OutboxMessage.enqueue_text(destination_phone="+525512345678", body="   ")


class TestEnqueueTemplate:
    def test_starts_pending_with_template_payload(self):
        message = OutboxMessage.enqueue_template(
            destination_phone="+525512345678", template_name="pedido_listo",
            parameters={"folio": "F-001"},
        )
        assert message.status == OutboxMessageStatus.PENDING
        assert message.template_name == "pedido_listo"
        assert message.payload["kind"] == "template"
        assert message.payload["language"] == "es_MX"
        assert message.payload["parameters"] == {"folio": "F-001"}

    def test_requires_template_name(self):
        with pytest.raises(ValueError):
            OutboxMessage.enqueue_template(destination_phone="+525512345678", template_name="")


class TestIsDue:
    def test_freshly_enqueued_is_due(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        assert message.is_due() is True

    def test_not_due_before_next_retry_at(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_failed("timeout")
        assert message.is_due() is False

    def test_due_after_next_retry_at_passes(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_failed("timeout")
        future = message.next_retry_at + timedelta(seconds=1)
        assert message.is_due(now=future) is True

    def test_terminal_message_is_never_due(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_sent()
        assert message.is_due() is False


class TestTransitions:
    def test_mark_sent_is_terminal(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_sent()
        assert message.status == OutboxMessageStatus.SENT
        assert message.processed_at is not None
        assert message.is_terminal()

    def test_mark_failed_schedules_retry_before_max_attempts(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_failed("timeout")
        assert message.status == OutboxMessageStatus.PENDING
        assert message.last_error == "timeout"
        assert message.next_retry_at is not None
        assert not message.is_terminal()

    def test_mark_failed_moves_to_dead_letter_after_max_attempts(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        for _ in range(MAX_ATTEMPTS):
            message.claim()
            message.mark_failed("timeout")
        assert message.status == OutboxMessageStatus.DEAD_LETTER
        assert message.is_terminal()

    def test_cannot_transition_a_sent_message(self):
        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_sent()
        with pytest.raises(OutboxMessageAlreadyFinalizedError):
            message.mark_failed("too late")
