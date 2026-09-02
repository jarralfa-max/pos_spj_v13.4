# tests/test_domain_whatsapp_conversation.py — WA-2
"""WhatsAppConversation, ConversationSession, ConversationContext."""
from __future__ import annotations

import pytest

from domain.whatsapp.entities.conversation import ConversationSession, WhatsAppConversation
from domain.whatsapp.entities.conversation_context import ConversationContext
from domain.whatsapp.enums import ConversationState
from domain.whatsapp.exceptions import InvalidConversationStateTransitionError


def _conversation(**overrides):
    defaults = dict(identity_id="identity-1", channel_number_id="number-1", branch_id="branch-1")
    defaults.update(overrides)
    return WhatsAppConversation.open(**defaults)


class TestWhatsAppConversationOpen:
    def test_starts_open(self):
        assert _conversation().state == ConversationState.OPEN

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7
        assert is_uuidv7(_conversation().id)

    def test_context_starts_at_version_1(self):
        assert _conversation().context.version == 1

    def test_context_seeds_branch_id(self):
        conversation = _conversation(branch_id="branch-9")
        assert conversation.context.branch_id == "branch-9"

    def test_requires_identity_id(self):
        with pytest.raises(ValueError):
            _conversation(identity_id="")

    def test_requires_channel_number_id(self):
        with pytest.raises(ValueError):
            _conversation(channel_number_id="")

    def test_no_active_session_initially(self):
        assert _conversation().current_session_id is None


class TestWhatsAppConversationTransitions:
    def test_transition_updates_state(self):
        conversation = _conversation()
        conversation.transition_to(ConversationState.BOT_ACTIVE)
        assert conversation.state == ConversationState.BOT_ACTIVE

    def test_closing_sets_closed_at(self):
        conversation = _conversation()
        conversation.transition_to(ConversationState.CLOSED)
        assert conversation.closed_at is not None

    def test_terminal_state_cannot_reopen(self):
        conversation = _conversation()
        conversation.transition_to(ConversationState.CLOSED)
        with pytest.raises(InvalidConversationStateTransitionError):
            conversation.transition_to(ConversationState.OPEN)

    def test_terminal_to_terminal_is_allowed(self):
        """P.ej. RESOLVED -> CLOSED, ambos terminales, es una transición de
        archivado válida, no una reapertura."""
        conversation = _conversation()
        conversation.transition_to(ConversationState.RESOLVED)
        conversation.transition_to(ConversationState.CLOSED)
        assert conversation.state == ConversationState.CLOSED

    @pytest.mark.parametrize(
        "terminal",
        [
            ConversationState.RESOLVED,
            ConversationState.CLOSED,
            ConversationState.EXPIRED,
            ConversationState.BLOCKED,
        ],
    )
    def test_is_terminal_true_for_all_terminal_states(self, terminal):
        conversation = _conversation()
        conversation.transition_to(terminal)
        assert conversation.is_terminal() is True

    def test_is_terminal_false_for_open(self):
        assert _conversation().is_terminal() is False


class TestWhatsAppConversationContextAndSession:
    def test_update_context_bumps_version(self):
        conversation = _conversation()
        conversation.update_context(active_order_draft_id="order-1")
        assert conversation.context.version == 2
        assert conversation.context.active_order_draft_id == "order-1"

    def test_update_context_preserves_other_fields(self):
        conversation = _conversation()
        conversation.update_context(customer_id="cust-1")
        conversation.update_context(active_quote_id="quote-1")
        assert conversation.context.customer_id == "cust-1"
        assert conversation.context.active_quote_id == "quote-1"

    def test_clear_active_flow_drops_flow_fields_only(self):
        context = ConversationContext(
            customer_id="cust-1",
            branch_id="branch-1",
            active_order_draft_id="order-1",
            expected_intent="CREATE_ORDER",
        )
        cleared = context.clear_active_flow()
        assert cleared.active_order_draft_id is None
        assert cleared.expected_intent is None
        assert cleared.customer_id == "cust-1"
        assert cleared.branch_id == "branch-1"

    def test_context_with_update_rejects_unknown_field(self):
        with pytest.raises(ValueError):
            ConversationContext().with_update(precio_total=100)

    def test_record_inbound_message_sets_last_message_at(self):
        conversation = _conversation()
        assert conversation.last_message_at is None
        conversation.record_inbound_message()
        assert conversation.last_message_at is not None

    def test_attach_session_from_same_conversation(self):
        conversation = _conversation()
        session = ConversationSession.start(conversation_id=conversation.id)
        conversation.attach_session(session)
        assert conversation.current_session_id == session.id

    def test_attach_session_from_other_conversation_rejected(self):
        conversation = _conversation()
        other_session = ConversationSession.start(conversation_id="other-conv")
        with pytest.raises(ValueError):
            conversation.attach_session(other_session)

    def test_session_ends_only_once(self):
        session = ConversationSession.start(conversation_id="conv-1")
        session.end()
        first_ended_at = session.ended_at
        session.end()
        assert session.ended_at == first_ended_at

    def test_session_is_active_until_ended(self):
        session = ConversationSession.start(conversation_id="conv-1")
        assert session.is_active() is True
        session.end()
        assert session.is_active() is False
