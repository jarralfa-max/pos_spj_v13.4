# domain/whatsapp/services/conversation_state_machine.py — WA-7 (§26)
"""
ConversationStateMachine — las reglas de "qué señal mueve una conversación
a qué estado", separadas del invariante mínimo que la propia entidad
`WhatsAppConversation` (WA-2) ya protege (un estado terminal no reabre).
Esta es la pieza que decide, la entidad es la que aplica y valida.

Una `ConversationSignal` es "qué pasó a nivel de conversación" — no una
`Intent` de negocio (§27, catálogo separado). Resolver qué intención tiene
el cliente es WA-8; decidir a qué estado mueve eso la conversación es esta
fase.
"""
from __future__ import annotations

from typing import Dict, Tuple

from domain.whatsapp.enums import TERMINAL_CONVERSATION_STATES, ConversationSignal, ConversationState

# Señales universales: aplican desde cualquier estado NO terminal, sin
# importar el estado actual (un bloqueo o un timeout puede ocurrir en
# cualquier punto de la conversación).
_UNIVERSAL_TRANSITIONS: Dict[ConversationSignal, ConversationState] = {
    ConversationSignal.BLOCK: ConversationState.BLOCKED,
    ConversationSignal.TIMEOUT: ConversationState.EXPIRED,
}

# Reglas específicas por estado — solo para señales que no son universales.
# Una entrada ausente para (estado, señal) es "esta señal no aplica en este
# estado" — ver `next_state()`.
_TRANSITIONS: Dict[Tuple[ConversationState, ConversationSignal], ConversationState] = {
    (ConversationState.OPEN, ConversationSignal.MESSAGE_RECEIVED): ConversationState.BOT_ACTIVE,
    (ConversationState.OPEN, ConversationSignal.HANDOFF_REQUESTED): ConversationState.HANDOFF_REQUESTED,

    (ConversationState.BOT_ACTIVE, ConversationSignal.MESSAGE_RECEIVED): ConversationState.BOT_ACTIVE,
    (ConversationState.BOT_ACTIVE, ConversationSignal.BOT_RESPONDED): ConversationState.WAITING_CUSTOMER,
    (ConversationState.BOT_ACTIVE, ConversationSignal.AWAITING_ERP_CONFIRMATION): ConversationState.WAITING_ERP,
    (ConversationState.BOT_ACTIVE, ConversationSignal.AWAITING_PAYMENT): ConversationState.WAITING_PAYMENT,
    (ConversationState.BOT_ACTIVE, ConversationSignal.APPROVAL_REQUIRED): ConversationState.WAITING_APPROVAL,
    (ConversationState.BOT_ACTIVE, ConversationSignal.HANDOFF_REQUESTED): ConversationState.HANDOFF_REQUESTED,
    (ConversationState.BOT_ACTIVE, ConversationSignal.RESOLVED): ConversationState.RESOLVED,

    (ConversationState.WAITING_CUSTOMER, ConversationSignal.MESSAGE_RECEIVED): ConversationState.BOT_ACTIVE,
    (ConversationState.WAITING_CUSTOMER, ConversationSignal.HANDOFF_REQUESTED): ConversationState.HANDOFF_REQUESTED,

    (ConversationState.WAITING_ERP, ConversationSignal.MESSAGE_RECEIVED): ConversationState.WAITING_ERP,
    (ConversationState.WAITING_ERP, ConversationSignal.BOT_RESPONDED): ConversationState.WAITING_CUSTOMER,
    (ConversationState.WAITING_ERP, ConversationSignal.RESOLVED): ConversationState.RESOLVED,
    (ConversationState.WAITING_ERP, ConversationSignal.HANDOFF_REQUESTED): ConversationState.HANDOFF_REQUESTED,

    (ConversationState.WAITING_PAYMENT, ConversationSignal.MESSAGE_RECEIVED): ConversationState.WAITING_PAYMENT,
    (ConversationState.WAITING_PAYMENT, ConversationSignal.RESOLVED): ConversationState.RESOLVED,
    (ConversationState.WAITING_PAYMENT, ConversationSignal.HANDOFF_REQUESTED): ConversationState.HANDOFF_REQUESTED,

    (ConversationState.WAITING_APPROVAL, ConversationSignal.MESSAGE_RECEIVED): ConversationState.BOT_ACTIVE,
    (ConversationState.WAITING_APPROVAL, ConversationSignal.RESOLVED): ConversationState.RESOLVED,
    (ConversationState.WAITING_APPROVAL, ConversationSignal.HANDOFF_REQUESTED): ConversationState.HANDOFF_REQUESTED,

    (ConversationState.HANDOFF_REQUESTED, ConversationSignal.MESSAGE_RECEIVED): ConversationState.HANDOFF_REQUESTED,
    (ConversationState.HANDOFF_REQUESTED, ConversationSignal.AGENT_JOINED): ConversationState.HUMAN_ACTIVE,

    (ConversationState.HUMAN_ACTIVE, ConversationSignal.MESSAGE_RECEIVED): ConversationState.HUMAN_ACTIVE,
    (ConversationState.HUMAN_ACTIVE, ConversationSignal.RESOLVED): ConversationState.RESOLVED,
}


class UnhandledConversationSignalError(RuntimeError):
    """La señal no tiene una regla definida para el estado actual — mejor
    fallar explícito que aplicar una transición adivinada."""


def next_state(current: ConversationState, signal: ConversationSignal) -> ConversationState:
    """Retorna el estado siguiente para `current` + `signal`.

    Un estado terminal siempre se ignora (retorna el mismo estado) salvo
    que la señal sea universal — mismo criterio que el invariante ya
    protegido por `WhatsAppConversation.transition_to()`, aplicado aquí un
    paso antes para no depender de que el llamador maneje la excepción.
    """
    if current in TERMINAL_CONVERSATION_STATES:
        return _UNIVERSAL_TRANSITIONS.get(signal, current)

    if signal in _UNIVERSAL_TRANSITIONS:
        return _UNIVERSAL_TRANSITIONS[signal]

    key = (current, signal)
    if key in _TRANSITIONS:
        return _TRANSITIONS[key]

    raise UnhandledConversationSignalError(
        f"Sin regla de transición para estado={current.value} señal={signal.value}"
    )
