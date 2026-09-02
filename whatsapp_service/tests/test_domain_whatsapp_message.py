# tests/test_domain_whatsapp_message.py — WA-2
"""WhatsAppMessage y WhatsAppMessageDelivery."""
from __future__ import annotations

import pytest

from domain.whatsapp.entities.message import WhatsAppMessage, WhatsAppMessageDelivery
from domain.whatsapp.enums import MessageDeliveryStatus, MessageDirection, MessageType
from domain.whatsapp.exceptions import InvalidMessageDeliveryTransitionError


class TestWhatsAppMessageCreate:
    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7
        message = WhatsAppMessage.create(
            conversation_id="conv-1",
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
        )
        assert is_uuidv7(message.id)

    def test_requires_conversation_id(self):
        with pytest.raises(ValueError):
            WhatsAppMessage.create(
                conversation_id="",
                direction=MessageDirection.INBOUND,
                message_type=MessageType.TEXT,
            )

    def test_defaults_are_none(self):
        message = WhatsAppMessage.create(
            conversation_id="conv-1",
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.TEMPLATE,
        )
        assert message.provider_message_id is None
        assert message.correlation_id is None
        assert message.operation_id is None


def _delivery():
    message = WhatsAppMessage.create(
        conversation_id="conv-1",
        direction=MessageDirection.OUTBOUND,
        message_type=MessageType.TEXT,
    )
    return WhatsAppMessageDelivery.create(message_id=message.id)


class TestWhatsAppMessageDeliveryCreate:
    def test_starts_queued(self):
        assert _delivery().status == MessageDeliveryStatus.QUEUED

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7
        assert is_uuidv7(_delivery().id)

    def test_attempt_count_starts_at_zero(self):
        assert _delivery().attempt_count == 0

    def test_requires_message_id(self):
        with pytest.raises(ValueError):
            WhatsAppMessageDelivery.create(message_id="")


class TestWhatsAppMessageDeliveryTransitions:
    def test_queued_to_sent_bumps_attempt_count(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        assert delivery.attempt_count == 1
        assert delivery.sent_at is not None

    def test_sent_to_delivered_sets_timestamp(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.DELIVERED)
        assert delivery.delivered_at is not None

    def test_delivered_to_read_sets_timestamp(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.DELIVERED)
        delivery.transition_to(MessageDeliveryStatus.READ)
        assert delivery.read_at is not None
        assert delivery.is_terminal() is True

    def test_failed_records_error_code(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.FAILED, error_code="TIMEOUT")
        assert delivery.error_code == "TIMEOUT"
        assert delivery.failed_at is not None

    def test_failed_can_retry(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.FAILED, error_code="TIMEOUT")
        delivery.transition_to(MessageDeliveryStatus.RETRYING)
        assert delivery.attempt_count == 2

    def test_retrying_can_go_back_to_sent(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.FAILED)
        delivery.transition_to(MessageDeliveryStatus.RETRYING)
        delivery.transition_to(MessageDeliveryStatus.SENT)
        assert delivery.status == MessageDeliveryStatus.SENT

    def test_dead_letter_is_terminal_and_final(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.FAILED)
        delivery.transition_to(MessageDeliveryStatus.DEAD_LETTER)
        assert delivery.is_terminal() is True
        with pytest.raises(InvalidMessageDeliveryTransitionError):
            delivery.transition_to(MessageDeliveryStatus.RETRYING)

    def test_cancelled_from_queued_is_valid(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.CANCELLED)
        assert delivery.is_terminal() is True

    def test_read_cannot_go_back_to_delivered(self):
        delivery = _delivery()
        delivery.transition_to(MessageDeliveryStatus.SENT)
        delivery.transition_to(MessageDeliveryStatus.DELIVERED)
        delivery.transition_to(MessageDeliveryStatus.READ)
        with pytest.raises(InvalidMessageDeliveryTransitionError):
            delivery.transition_to(MessageDeliveryStatus.DELIVERED)

    def test_queued_cannot_jump_directly_to_read(self):
        delivery = _delivery()
        with pytest.raises(InvalidMessageDeliveryTransitionError):
            delivery.transition_to(MessageDeliveryStatus.READ)
