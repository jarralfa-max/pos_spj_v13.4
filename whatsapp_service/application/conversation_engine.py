# application/conversation_engine.py — WA-7 (§26 del prompt maestro)
"""
ConversationEngine — orquesta `ConversationStateMachine` (dominio, WA-7)
más timeout y reset sobre una `WhatsAppConversation` real (WA-2), y
persiste el resultado vía `WhatsAppConversationRepository` (WA-4).

No resuelve intención (WA-8) ni ejecuta lógica de negocio (WA-9+) — solo
decide y aplica transición de estado + maneja el ciclo de vida genérico de
la conversación (timeout/reset). Candidato natural para ser el `handler`
de `InboxWorker` (WA-6) una vez que WA-8 pueda proveerle una señal real a
partir de un mensaje entrante — esa integración queda para cuando WA-8
exista, no se fuerza aquí con una señal inventada.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.enums import ConversationSignal, ConversationState
from domain.whatsapp.services.conversation_state_machine import next_state


class CannotResetTerminalConversationError(RuntimeError):
    """Una conversación en estado terminal no se "reinicia in-place" — el
    invariante de `WhatsAppConversation.transition_to()` (WA-2) lo prohíbe
    a propósito. Iniciar una conversación nueva para la misma identidad es
    la operación correcta (`WhatsAppConversation.open()` +
    `WhatsAppConversationRepository.get_open_for_identity`, que ya
    devuelve `None` cuando la única conversación previa está cerrada)."""


class ConversationEngine:
    def __init__(self, root) -> None:
        self._root = root

    def handle_signal(
        self, conversation: WhatsAppConversation, signal: ConversationSignal
    ) -> WhatsAppConversation:
        """Aplica la señal, persiste si el estado cambió, retorna la
        conversación (misma instancia, mutada)."""
        target = next_state(conversation.state, signal)
        if target != conversation.state:
            conversation.transition_to(target)
            self._root.conversations.save(conversation)
        return conversation

    def check_timeout(
        self,
        conversation: WhatsAppConversation,
        *,
        now: Optional[datetime] = None,
        timeout_minutes: Optional[int] = None,
    ) -> bool:
        """True si la conversación debía expirar y se le aplicó
        `ConversationSignal.TIMEOUT` (mutó y se persistió). False si no
        aplicaba (ya terminal, o todavía dentro de la ventana).

        `timeout_minutes` por defecto lee
        `config.settings.CONVERSATION_TIMEOUT_MINUTES` — no se
        reintroduce un default nuevo, se reutiliza el ya existente.
        """
        if conversation.is_terminal():
            return False

        if timeout_minutes is None:
            from config.settings import CONVERSATION_TIMEOUT_MINUTES

            timeout_minutes = CONVERSATION_TIMEOUT_MINUTES

        reference = conversation.last_message_at or conversation.opened_at
        current_time = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        if current_time - reference < timedelta(minutes=timeout_minutes):
            return False

        self.handle_signal(conversation, ConversationSignal.TIMEOUT)
        return True

    def reset(self, conversation: WhatsAppConversation) -> WhatsAppConversation:
        """Limpia el flujo activo (§14/§31, `clear_active_flow`) y regresa
        el estado a OPEN. Rechaza conversaciones terminales — ver
        `CannotResetTerminalConversationError`."""
        if conversation.is_terminal():
            raise CannotResetTerminalConversationError(
                f"Conversación {conversation.id} está en estado terminal "
                f"{conversation.state.value}; no se puede reiniciar in-place"
            )
        conversation.context = conversation.context.clear_active_flow()
        conversation.transition_to(ConversationState.OPEN)
        self._root.conversations.save(conversation)
        return conversation
