# tests/test_intent_resolution_service.py — WA-8
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from application.intent_resolution_service import (
    IntentResolutionService,
    NullIntentAIProvider,
    intent_to_conversation_signal,
)
from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.enums import ConversationSignal, Intent
from domain.whatsapp.value_objects.intent_resolution import IntentResolution, IntentResolutionSource
from models.message import IncomingMessage, InteractiveType, MessageType


def _conversation(**context_overrides) -> WhatsAppConversation:
    conversation = WhatsAppConversation.open(identity_id="identity-1", channel_number_id="number-1")
    if context_overrides:
        conversation.update_context(**context_overrides)
    return conversation


def _incoming(**overrides) -> IncomingMessage:
    defaults = dict(
        message_id="wamid.1", from_number="5512345678", phone_number_id="phone-1",
        timestamp=datetime.now(), type=MessageType.TEXT, text="",
    )
    defaults.update(overrides)
    return IncomingMessage(**defaults)


def _resolve(service, incoming, conversation) -> IntentResolution:
    return asyncio.run(service.resolve(incoming=incoming, conversation=conversation))


class TestLayer1Interactive:
    def test_known_interactive_id_resolves_deterministically(self):
        service = IntentResolutionService()
        incoming = _incoming(
            type=MessageType.INTERACTIVE, interactive_type=InteractiveType.BUTTON_REPLY,
            interactive_id="menu_pedido", text="",
        )
        result = _resolve(service, incoming, _conversation())
        assert result.intent == Intent.CREATE_ORDER
        assert result.source == IntentResolutionSource.INTERACTIVE
        assert result.confidence == 1.0

    def test_interactive_wins_over_expected_state_and_text(self):
        service = IntentResolutionService()
        incoming = _incoming(
            type=MessageType.INTERACTIVE, interactive_id="menu_cotizacion", text="hola",
        )
        conversation = _conversation(expected_intent=Intent.CREATE_ORDER.value)
        result = _resolve(service, incoming, conversation)
        assert result.intent == Intent.CREATE_QUOTE
        assert result.source == IntentResolutionSource.INTERACTIVE

    def test_unknown_interactive_id_falls_through_to_later_layers(self):
        service = IntentResolutionService()
        incoming = _incoming(interactive_id="some_unmapped_button", text="hola")
        result = _resolve(service, incoming, _conversation())
        assert result.source != IntentResolutionSource.INTERACTIVE


class TestLayer2ExpectedState:
    def test_expected_intent_resolves_when_no_interactive(self):
        service = IntentResolutionService()
        conversation = _conversation(expected_intent=Intent.CHECK_STOCK.value)
        result = _resolve(service, _incoming(text="algo"), conversation)
        assert result.intent == Intent.CHECK_STOCK
        assert result.source == IntentResolutionSource.EXPECTED_STATE

    def test_invalid_expected_intent_value_falls_through(self):
        service = IntentResolutionService()
        conversation = _conversation()
        conversation.context = conversation.context.with_update(expected_intent="NOT_A_REAL_INTENT")
        result = _resolve(service, _incoming(text="hola"), conversation)
        assert result.source != IntentResolutionSource.EXPECTED_STATE


class TestLayer3Rules:
    def test_greeting_keyword_matches(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text="Hola buenas tardes"), _conversation())
        assert result.intent == Intent.GREETING
        assert result.source == IntentResolutionSource.RULE

    def test_help_keyword_matches(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text="necesito ayuda"), _conversation())
        assert result.intent == Intent.HELP

    def test_opt_out_keyword_matches(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text="STOP"), _conversation())
        assert result.intent == Intent.OPT_OUT

    def test_human_handoff_keyword_matches(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text="quiero hablar con alguien"), _conversation())
        assert result.intent == Intent.HUMAN_HANDOFF
        assert result.source == IntentResolutionSource.RULE

    def test_unmatched_free_text_does_not_match_rules(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text="xyzxyz sin sentido"), _conversation())
        assert result.source != IntentResolutionSource.RULE


class TestLayers4And5AiProvider:
    def test_null_provider_always_returns_none(self):
        result = asyncio.run(NullIntentAIProvider().classify(text="algo", context={}))
        assert result is None

    def test_ai_provider_result_used_when_rules_do_not_match(self):
        class _FakeAI:
            async def classify(self, *, text, context):
                return IntentResolution(intent=Intent.SEARCH_PRODUCT, confidence=0.6, source=IntentResolutionSource.CLASSIFIER)

        service = IntentResolutionService(ai_provider=_FakeAI())
        result = _resolve(service, _incoming(text="quiero bistec"), _conversation())
        assert result.intent == Intent.SEARCH_PRODUCT
        assert result.source == IntentResolutionSource.CLASSIFIER

    def test_ai_provider_not_called_when_a_rule_already_matched(self):
        called = {"n": 0}

        class _FakeAI:
            async def classify(self, *, text, context):
                called["n"] += 1
                return IntentResolution(intent=Intent.UNKNOWN, confidence=0.5, source=IntentResolutionSource.CLASSIFIER)

        service = IntentResolutionService(ai_provider=_FakeAI())
        _resolve(service, _incoming(text="hola"), _conversation())
        assert called["n"] == 0

    def test_ai_provider_not_called_for_empty_text(self):
        called = {"n": 0}

        class _FakeAI:
            async def classify(self, *, text, context):
                called["n"] += 1
                return None

        service = IntentResolutionService(ai_provider=_FakeAI())
        _resolve(service, _incoming(text=""), _conversation())
        assert called["n"] == 0


class TestLayer6HumanHandoffFallback:
    def test_unresolved_text_falls_back_to_human_handoff(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text="asdkjaslkdj"), _conversation())
        assert result.intent == Intent.HUMAN_HANDOFF
        assert result.source == IntentResolutionSource.UNRESOLVED
        assert result.is_resolved is False

    def test_empty_text_falls_back_to_human_handoff(self):
        service = IntentResolutionService()
        result = _resolve(service, _incoming(text=""), _conversation())
        assert result.intent == Intent.HUMAN_HANDOFF


class TestIntentToConversationSignal:
    def test_human_handoff_intent_maps_to_handoff_signal(self):
        resolution = IntentResolution(intent=Intent.HUMAN_HANDOFF, confidence=0.0, source=IntentResolutionSource.UNRESOLVED)
        assert intent_to_conversation_signal(resolution) == ConversationSignal.HANDOFF_REQUESTED

    def test_opt_out_intent_maps_to_handoff_signal(self):
        resolution = IntentResolution(intent=Intent.OPT_OUT, confidence=0.7, source=IntentResolutionSource.RULE)
        assert intent_to_conversation_signal(resolution) == ConversationSignal.HANDOFF_REQUESTED

    def test_business_intent_maps_to_message_received(self):
        resolution = IntentResolution(intent=Intent.CREATE_ORDER, confidence=1.0, source=IntentResolutionSource.INTERACTIVE)
        assert intent_to_conversation_signal(resolution) == ConversationSignal.MESSAGE_RECEIVED
