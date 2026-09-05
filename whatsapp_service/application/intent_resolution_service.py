# application/intent_resolution_service.py — WA-8 (§28 del prompt maestro)
"""
IntentResolutionService — resolución de intención por capas, en el orden
exacto que pide §28:

    1. Interactive reply determinista.
    2. State-machine expected response (ConversationContext.expected_intent).
    3. Regla/regex segura.
    4-5. Intent classifier / LLM fallback (mismo puerto `IntentAIProvider`,
         §29 — la implementación real decide internamente si usa un
         clasificador local o un LLM; esta fase solo define el punto de
         entrada y el orden en que se invoca).
    6. Human handoff — si nada anterior resolvió, no se inventa una
       intención de bajo alcance.

Se detiene en la primera capa que resuelve — nunca sigue "por si acaso"
una capa posterior es más precisa. El LLM/clasificador (capas 4-5) **nunca
ejecuta una operación de negocio** — solo devuelve una `IntentResolution`;
ejecutar lo que esa intención implica es trabajo de fases futuras (WA-9+).
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.enums import Intent
from domain.whatsapp.provider_ports import IntentAIProvider
from domain.whatsapp.value_objects.intent_resolution import (
    IntentEntity,
    IntentResolution,
    IntentResolutionSource,
)
from models.message import IncomingMessage

# ── Capa 1 — Interactive reply determinista ─────────────────────────────────
# IDs reales que ya usan los botones/listas de `messaging/interactive.py` —
# no inventados; reflejan la UI conversacional que ya está en producción.
_INTERACTIVE_ID_TO_INTENT: Dict[str, Intent] = {
    "menu_pedido": Intent.CREATE_ORDER,
    "menu_cotizacion": Intent.CREATE_QUOTE,
    "menu_estado": Intent.CHECK_ORDER_STATUS,
    "menu_repetir": Intent.CREATE_ORDER,
    "menu_sucursal": Intent.SELECT_BRANCH,
    "menu_ayuda": Intent.HELP,
    "mas_agregar": Intent.UPDATE_ORDER,
    "mas_confirmar": Intent.CREATE_ORDER,
    "cancel_pedido": Intent.CANCEL_ORDER,
    "cancel_ok": Intent.CANCEL_ORDER,
    "entrega_sucursal": Intent.SCHEDULE_DELIVERY,
    "entrega_domicilio": Intent.SCHEDULE_DELIVERY,
    "pago_efectivo": Intent.PAY_ORDER,
    "pago_link": Intent.PAY_ORDER,
    "pago_terminal": Intent.PAY_ORDER,
}

# ── Capa 3 — Reglas/regex seguras sobre texto libre ─────────────────────────
# Coincidencia simple por subcadena en minúsculas — deliberadamente
# acotado: no intenta ser el clasificador (eso son las capas 4-5).
_RULE_KEYWORDS: Tuple[Tuple[Intent, Tuple[str, ...]], ...] = (
    (Intent.OPT_OUT, ("baja", "stop", "cancelar promociones", "no mas mensajes", "no más mensajes")),
    (Intent.HUMAN_HANDOFF, ("hablar con alguien", "hablar con una persona", "agente humano", "asesor")),
    (Intent.HELP, ("ayuda", "help", "no entiendo", "no entendi")),
    (Intent.GREETING, ("hola", "buenas", "buenos dias", "buenos días", "buenas tardes", "buenas noches")),
    (Intent.SHOW_MENU, ("menu", "menú", "opciones", "que puedo hacer")),
    (Intent.CANCEL_ORDER, ("cancelar pedido", "cancelar mi pedido")),
    (Intent.CHECK_ORDER_STATUS, ("mi pedido", "estado de mi pedido", "donde esta mi pedido", "dónde está mi pedido")),
    (Intent.TRACK_DELIVERY, ("donde esta el repartidor", "dónde está el repartidor", "seguimiento")),
    (Intent.CHECK_LOYALTY, ("mis puntos", "puntos acumulados")),
)


class NullIntentAIProvider:
    """`IntentAIProvider` sin clasificador ni LLM conectados todavía —
    siempre `None`. Documenta el estado real en vez de fingir uno: hoy no
    hay ninguna implementación de clasificador/LLM wireada en el
    `CompositionRoot` (la versión legacy, `ai/intent_resolver.py`, existe
    pero no se conectó aquí — depende de `ProductMatcher`/`OllamaClient`,
    infraestructura de catálogo que es más bien alcance de WA-9). Usarla
    fuerza siempre el fallback a human handoff (capa 6), nunca inventa una
    intención de bajo alcance."""

    async def classify(self, *, text: str, context: Dict) -> Optional[IntentResolution]:
        return None


class IntentResolutionService:
    def __init__(self, ai_provider: Optional[IntentAIProvider] = None) -> None:
        self._ai_provider = ai_provider or NullIntentAIProvider()

    async def resolve(
        self, *, incoming: IncomingMessage, conversation: WhatsAppConversation
    ) -> IntentResolution:
        # Capa 1 — interactive.
        if incoming.interactive_id:
            intent = _INTERACTIVE_ID_TO_INTENT.get(incoming.interactive_id)
            if intent is not None:
                return IntentResolution(
                    intent=intent,
                    confidence=1.0,
                    source=IntentResolutionSource.INTERACTIVE,
                    entities=(
                        IntentEntity(
                            name="interactive_id", value=incoming.interactive_id,
                            normalized_value=incoming.interactive_id, confidence=1.0, source="interactive",
                        ),
                    ),
                )

        # Capa 2 — estado esperado por la conversación (§31: expected_intent).
        expected = conversation.context.expected_intent
        if expected:
            try:
                return IntentResolution(
                    intent=Intent(expected), confidence=0.9, source=IntentResolutionSource.EXPECTED_STATE
                )
            except ValueError:
                pass  # expected_intent no es un Intent válido — sigue a las demás capas.

        text = (incoming.text or "").strip().lower()

        # Capa 3 — reglas/regex.
        if text:
            for intent, keywords in _RULE_KEYWORDS:
                if any(keyword in text for keyword in keywords):
                    return IntentResolution(intent=intent, confidence=0.7, source=IntentResolutionSource.RULE)

        # Capas 4-5 — clasificador / LLM (mismo puerto).
        if text:
            ai_result = await self._ai_provider.classify(
                text=text,
                context={
                    "customer_id": conversation.context.customer_id,
                    "branch_id": conversation.context.branch_id,
                    "expected_intent": conversation.context.expected_intent,
                },
            )
            if ai_result is not None:
                return ai_result

        # Capa 6 — human handoff (nunca se inventa una intención de bajo alcance).
        return IntentResolution(intent=Intent.HUMAN_HANDOFF, confidence=0.0, source=IntentResolutionSource.UNRESOLVED)


# ── Puente hacia ConversationEngine (WA-7) ──────────────────────────────────
# Qué intención produce qué señal de conversación. Deliberadamente
# conservador: ninguna intención de negocio (CREATE_ORDER, PAY_ORDER...)
# tiene todavía un caso de uso real que la ejecute (WA-9+), así que today
# todas mantienen la conversación activa (`MESSAGE_RECEIVED`) salvo las que
# genuinamente implican salir del control del bot.
_HANDOFF_INTENTS = frozenset({Intent.HUMAN_HANDOFF, Intent.OPT_OUT})


def intent_to_conversation_signal(resolution: IntentResolution):
    from domain.whatsapp.enums import ConversationSignal

    if resolution.intent in _HANDOFF_INTENTS:
        return ConversationSignal.HANDOFF_REQUESTED
    return ConversationSignal.MESSAGE_RECEIVED
