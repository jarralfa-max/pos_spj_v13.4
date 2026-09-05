# tests/test_conversation_state_machine.py — WA-7
from __future__ import annotations

import pytest

from domain.whatsapp.enums import ConversationSignal, ConversationState
from domain.whatsapp.services.conversation_state_machine import (
    UnhandledConversationSignalError,
    next_state,
)


class TestNormalFlow:
    def test_open_message_received_moves_to_bot_active(self):
        assert next_state(ConversationState.OPEN, ConversationSignal.MESSAGE_RECEIVED) == ConversationState.BOT_ACTIVE

    def test_bot_active_bot_responded_moves_to_waiting_customer(self):
        assert (
            next_state(ConversationState.BOT_ACTIVE, ConversationSignal.BOT_RESPONDED)
            == ConversationState.WAITING_CUSTOMER
        )

    def test_waiting_customer_message_received_returns_to_bot_active(self):
        assert (
            next_state(ConversationState.WAITING_CUSTOMER, ConversationSignal.MESSAGE_RECEIVED)
            == ConversationState.BOT_ACTIVE
        )

    def test_bot_active_awaiting_erp_confirmation_moves_to_waiting_erp(self):
        assert (
            next_state(ConversationState.BOT_ACTIVE, ConversationSignal.AWAITING_ERP_CONFIRMATION)
            == ConversationState.WAITING_ERP
        )

    def test_bot_active_awaiting_payment_moves_to_waiting_payment(self):
        assert (
            next_state(ConversationState.BOT_ACTIVE, ConversationSignal.AWAITING_PAYMENT)
            == ConversationState.WAITING_PAYMENT
        )

    def test_bot_active_approval_required_moves_to_waiting_approval(self):
        assert (
            next_state(ConversationState.BOT_ACTIVE, ConversationSignal.APPROVAL_REQUIRED)
            == ConversationState.WAITING_APPROVAL
        )

    def test_waiting_approval_message_received_moves_to_bot_active(self):
        assert (
            next_state(ConversationState.WAITING_APPROVAL, ConversationSignal.MESSAGE_RECEIVED)
            == ConversationState.BOT_ACTIVE
        )

    @pytest.mark.parametrize(
        "state",
        [
            ConversationState.BOT_ACTIVE,
            ConversationState.WAITING_ERP,
            ConversationState.WAITING_PAYMENT,
            ConversationState.WAITING_APPROVAL,
            ConversationState.HUMAN_ACTIVE,
        ],
    )
    def test_resolved_signal_moves_to_resolved(self, state):
        assert next_state(state, ConversationSignal.RESOLVED) == ConversationState.RESOLVED


class TestHandoff:
    @pytest.mark.parametrize(
        "state",
        [
            ConversationState.OPEN,
            ConversationState.BOT_ACTIVE,
            ConversationState.WAITING_CUSTOMER,
            ConversationState.WAITING_ERP,
            ConversationState.WAITING_PAYMENT,
            ConversationState.WAITING_APPROVAL,
        ],
    )
    def test_handoff_requested_from_any_active_state(self, state):
        assert (
            next_state(state, ConversationSignal.HANDOFF_REQUESTED)
            == ConversationState.HANDOFF_REQUESTED
        )

    def test_agent_joined_moves_to_human_active(self):
        assert (
            next_state(ConversationState.HANDOFF_REQUESTED, ConversationSignal.AGENT_JOINED)
            == ConversationState.HUMAN_ACTIVE
        )

    def test_handoff_requested_stays_put_on_more_messages(self):
        assert (
            next_state(ConversationState.HANDOFF_REQUESTED, ConversationSignal.MESSAGE_RECEIVED)
            == ConversationState.HANDOFF_REQUESTED
        )


class TestUniversalSignals:
    @pytest.mark.parametrize(
        "state",
        [
            ConversationState.OPEN,
            ConversationState.BOT_ACTIVE,
            ConversationState.WAITING_CUSTOMER,
            ConversationState.WAITING_ERP,
            ConversationState.WAITING_PAYMENT,
            ConversationState.WAITING_APPROVAL,
            ConversationState.HANDOFF_REQUESTED,
            ConversationState.HUMAN_ACTIVE,
        ],
    )
    def test_block_always_moves_to_blocked(self, state):
        assert next_state(state, ConversationSignal.BLOCK) == ConversationState.BLOCKED

    @pytest.mark.parametrize(
        "state",
        [
            ConversationState.OPEN,
            ConversationState.BOT_ACTIVE,
            ConversationState.WAITING_CUSTOMER,
            ConversationState.HANDOFF_REQUESTED,
        ],
    )
    def test_timeout_always_moves_to_expired(self, state):
        assert next_state(state, ConversationSignal.TIMEOUT) == ConversationState.EXPIRED


class TestTerminalStatesIgnoreNonUniversalSignals:
    @pytest.mark.parametrize(
        "state",
        [
            ConversationState.RESOLVED,
            ConversationState.CLOSED,
            ConversationState.EXPIRED,
            ConversationState.BLOCKED,
        ],
    )
    def test_message_received_on_terminal_state_is_a_no_op(self, state):
        assert next_state(state, ConversationSignal.MESSAGE_RECEIVED) == state

    def test_universal_signal_still_applies_on_terminal_state(self):
        # BLOCK sigue moviendo aunque ya esté RESOLVED (auditar el bloqueo,
        # no ignorarlo silenciosamente).
        assert next_state(ConversationState.RESOLVED, ConversationSignal.BLOCK) == ConversationState.BLOCKED


class TestUnhandledSignal:
    def test_raises_for_undefined_state_signal_pair(self):
        with pytest.raises(UnhandledConversationSignalError):
            next_state(ConversationState.HUMAN_ACTIVE, ConversationSignal.AWAITING_PAYMENT)
