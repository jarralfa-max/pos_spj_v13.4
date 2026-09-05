# tests/test_conversation_engine.py — WA-7
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from application.conversation_engine import CannotResetTerminalConversationError, ConversationEngine
from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.composition_root import WhatsAppCompositionRoot
from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.enums import ConversationSignal, ConversationState


@pytest.fixture()
def root():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    r = WhatsAppCompositionRoot(connection)
    yield r
    connection.close()


def _open_conversation(root) -> WhatsAppConversation:
    conversation = WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1")
    root.conversations.save(conversation)
    return conversation


class TestHandleSignal:
    def test_transitions_and_persists_on_change(self, root):
        conversation = _open_conversation(root)
        engine = ConversationEngine(root)
        engine.handle_signal(conversation, ConversationSignal.MESSAGE_RECEIVED)
        assert conversation.state == ConversationState.BOT_ACTIVE
        assert root.conversations.get_by_id(conversation.id).state == ConversationState.BOT_ACTIVE

    def test_no_op_signal_does_not_change_updated_at_again(self, root):
        conversation = _open_conversation(root)
        engine = ConversationEngine(root)
        engine.handle_signal(conversation, ConversationSignal.MESSAGE_RECEIVED)  # OPEN -> BOT_ACTIVE
        after_first = conversation.updated_at
        engine.handle_signal(conversation, ConversationSignal.MESSAGE_RECEIVED)  # BOT_ACTIVE -> BOT_ACTIVE, no-op
        assert conversation.updated_at == after_first

    def test_composition_root_exposes_engine(self, root):
        assert isinstance(root.conversation_engine, ConversationEngine)


class TestCheckTimeout:
    def test_false_when_within_window(self, root):
        conversation = _open_conversation(root)
        engine = ConversationEngine(root)
        now = conversation.opened_at + timedelta(minutes=5)
        assert engine.check_timeout(conversation, now=now, timeout_minutes=30) is False
        assert conversation.state == ConversationState.OPEN

    def test_true_and_expires_when_past_window(self, root):
        conversation = _open_conversation(root)
        engine = ConversationEngine(root)
        now = conversation.opened_at + timedelta(minutes=31)
        assert engine.check_timeout(conversation, now=now, timeout_minutes=30) is True
        assert conversation.state == ConversationState.EXPIRED
        assert root.conversations.get_by_id(conversation.id).state == ConversationState.EXPIRED

    def test_false_when_already_terminal(self, root):
        conversation = _open_conversation(root)
        conversation.transition_to(ConversationState.CLOSED)
        root.conversations.save(conversation)
        engine = ConversationEngine(root)
        now = conversation.opened_at + timedelta(days=1)
        assert engine.check_timeout(conversation, now=now, timeout_minutes=30) is False

    def test_uses_last_message_at_over_opened_at_when_present(self, root):
        conversation = _open_conversation(root)
        conversation.opened_at = conversation.opened_at - timedelta(hours=2)  # abierta hace mucho
        conversation.record_inbound_message()  # last_message_at = ahora (real, reciente)
        engine = ConversationEngine(root)
        # Solo 5 minutos desde el último mensaje real — no debe expirar,
        # aunque `opened_at` sea de hace 2 horas.
        now = conversation.last_message_at + timedelta(minutes=5)
        assert engine.check_timeout(conversation, now=now, timeout_minutes=30) is False

    def test_defaults_to_config_timeout_when_not_specified(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.CONVERSATION_TIMEOUT_MINUTES", 10)
        conversation = _open_conversation(root)
        engine = ConversationEngine(root)
        now = conversation.opened_at + timedelta(minutes=11)
        assert engine.check_timeout(conversation, now=now) is True


class TestReset:
    def test_clears_active_flow_and_returns_to_open(self, root):
        conversation = _open_conversation(root)
        conversation.transition_to(ConversationState.BOT_ACTIVE)
        conversation.update_context(active_order_draft_id="order-1", expected_intent="CREATE_ORDER")
        root.conversations.save(conversation)

        engine = ConversationEngine(root)
        engine.reset(conversation)

        assert conversation.state == ConversationState.OPEN
        assert conversation.context.active_order_draft_id is None
        assert conversation.context.expected_intent is None

        fetched = root.conversations.get_by_id(conversation.id)
        assert fetched.state == ConversationState.OPEN

    def test_raises_when_conversation_is_terminal(self, root):
        conversation = _open_conversation(root)
        conversation.transition_to(ConversationState.RESOLVED)
        root.conversations.save(conversation)

        engine = ConversationEngine(root)
        with pytest.raises(CannotResetTerminalConversationError):
            engine.reset(conversation)

    def test_preserves_customer_and_branch_context(self, root):
        conversation = _open_conversation(root)
        conversation.update_context(customer_id="cust-1", branch_id="branch-1")
        root.conversations.save(conversation)

        engine = ConversationEngine(root)
        engine.reset(conversation)

        assert conversation.context.customer_id == "cust-1"
        assert conversation.context.branch_id == "branch-1"
