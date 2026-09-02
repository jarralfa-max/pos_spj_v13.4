# tests/test_domain_whatsapp_events.py — WA-2
"""Eventos de dominio del canal WhatsApp (objetos puros, sin EventBus)."""
from __future__ import annotations

from datetime import datetime

from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.entities.message import WhatsAppMessage
from domain.whatsapp.enums import ConversationState, MessageDirection, MessageType
from domain.whatsapp.events import (
    ConversationOpened,
    ConversationStateChanged,
    IdentityBlocked,
    IdentityResolved,
    MessageDeduplicated,
    MessageDeliveryStatusChanged,
    MessageReceived,
    WHATSAPP_CONVERSATION_OPENED,
    WHATSAPP_MESSAGE_RECEIVED,
)
from domain.whatsapp.enums import MessageDeliveryStatus


class TestConversationOpenedEvent:
    def test_of_captures_conversation_fields(self):
        conversation = WhatsAppConversation.open(
            identity_id="identity-1", channel_number_id="number-1", branch_id="branch-1"
        )
        event = ConversationOpened.of(conversation)
        assert event.conversation_id == conversation.id
        assert event.identity_id == "identity-1"
        assert event.channel_number_id == "number-1"
        assert event.branch_id == "branch-1"
        assert event.occurred_at is not None

    def test_is_frozen(self):
        conversation = WhatsAppConversation.open(identity_id="i", channel_number_id="n")
        event = ConversationOpened.of(conversation)
        try:
            event.conversation_id = "tampered"  # type: ignore[misc]
            assert False, "se esperaba FrozenInstanceError"
        except Exception:
            pass


class TestConversationStateChangedEvent:
    def test_holds_previous_and_new_state(self):
        event = ConversationStateChanged(
            occurred_at=datetime.now(),
            conversation_id="conv-1",
            previous_state=ConversationState.OPEN,
            new_state=ConversationState.CLOSED,
        )
        assert event.previous_state == ConversationState.OPEN
        assert event.new_state == ConversationState.CLOSED


class TestMessageReceivedEvent:
    def test_of_captures_message_fields(self):
        message = WhatsAppMessage.create(
            conversation_id="conv-1",
            direction=MessageDirection.INBOUND,
            message_type=MessageType.TEXT,
            provider_message_id="wamid.123",
        )
        event = MessageReceived.of(message)
        assert event.message_id == message.id
        assert event.conversation_id == "conv-1"
        assert event.provider_message_id == "wamid.123"


class TestOtherDomainEvents:
    def test_message_deduplicated_holds_provider_id(self):
        event = MessageDeduplicated(
            occurred_at=datetime.now(),
            provider_message_id="wamid.123",
            conversation_id="conv-1",
        )
        assert event.provider_message_id == "wamid.123"

    def test_message_delivery_status_changed(self):
        event = MessageDeliveryStatusChanged(
            occurred_at=datetime.now(),
            delivery_id="delivery-1",
            message_id="message-1",
            previous_status=MessageDeliveryStatus.SENT,
            new_status=MessageDeliveryStatus.FAILED,
            error_code="TIMEOUT",
        )
        assert event.error_code == "TIMEOUT"

    def test_identity_resolved_and_blocked(self):
        resolved = IdentityResolved(
            occurred_at=datetime.now(),
            identity_id="identity-1",
            customer_id="cust-1",
        )
        blocked = IdentityBlocked(
            occurred_at=datetime.now(), identity_id="identity-1"
        )
        assert resolved.customer_id == "cust-1"
        assert blocked.identity_id == "identity-1"


class TestCanonicalEventNames:
    def test_names_match_master_prompt_section_55(self):
        assert WHATSAPP_CONVERSATION_OPENED == "WHATSAPP_CONVERSATION_OPENED"
        assert WHATSAPP_MESSAGE_RECEIVED == "WHATSAPP_MESSAGE_RECEIVED"
