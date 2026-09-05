# application/handoff_service.py — WA-16 (§32 del prompt maestro)
"""
HandoffCoordinator — el reemplazo, dentro del bounded context nuevo, de
`middleware/handoff.py::HandoffService.escalar()` (legacy, sigue vivo y
sin tocar — mismo criterio de "paralelo, no conectado todavía" que cada
fase anterior). Cubre lo mismo que el legacy (notificar staff + avisar al
cliente) más lo que el legacy no tenía: un registro persistente de la
solicitud (`HandoffRequest`) y una transición real de
`ConversationState` vía `ConversationEngine` (WA-7) — el legacy no toca
el estado de conversación en absoluto.

Idempotente por diseño simple (no por fingerprint/§19): si ya hay una
`HandoffRequest` abierta (OPEN/ASSIGNED) para la conversación, no se
vuelve a notificar al staff — evita spamear al mismo gerente si el
cliente insiste "hablar con alguien" varias veces mientras espera.

**Envío síncrono, no vía outbox**: WA-17 (Outbox worker) todavía no
existe en este punto del árbol — igual que el legacy `HandoffService` y
que WA-1..15 en su totalidad (nada en el canal usa `whatsapp_outbox`
todavía), esto envía directo vía `ProviderGateway` (WA-5). Cuando WA-17
exista, es un candidato natural para migrar a outbox — no se fuerza esa
dependencia hacia adelante desde aquí.
"""
from __future__ import annotations

from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.entities.handoff_request import HandoffRequest
from domain.whatsapp.enums import ConversationSignal


class HandoffCoordinator:
    def __init__(self, root) -> None:
        self._root = root

    async def request_handoff(
        self, conversation: WhatsAppConversation, *, customer_phone: str, reason: str, branch_id: str = "",
    ) -> HandoffRequest:
        existing = self._root.handoff_requests.get_open_for_conversation(conversation.id)
        if existing is not None:
            return existing

        request = HandoffRequest.open(conversation_id=conversation.id, reason=reason, branch_id=branch_id or None)
        self._root.handoff_requests.save(request)

        self._root.conversation_engine.handle_signal(conversation, ConversationSignal.HANDOFF_REQUESTED)

        staff_phones = await self._root.staff_directory.get_staff_phones(branch_id, role="gerente")
        if not staff_phones:
            staff_phones = await self._root.staff_directory.get_staff_phones(branch_id)

        for staff_phone in staff_phones[:3]:
            await self._root.provider_gateway.send_text(
                to=staff_phone,
                body=(
                    "🆘 *Atención requerida*\n\n"
                    f"Cliente: {customer_phone}\n"
                    f"Motivo: {reason}\n\n"
                    "Responde directamente al cliente desde WhatsApp."
                ),
            )
        await self._root.provider_gateway.send_text(
            to=customer_phone,
            body="👤 Te estamos comunicando con un asesor.\nResponderá en unos minutos. ¡Gracias por tu paciencia!",
        )

        if staff_phones:
            request.assign(staff_phones[0])
            self._root.handoff_requests.save(request)

        return request

    def resolve(self, request_id: str) -> HandoffRequest:
        request = self._root.handoff_requests.get_by_id(request_id)
        if request is None:
            raise ValueError(f"HandoffRequest {request_id} no encontrado")
        request.resolve()
        self._root.handoff_requests.save(request)
        return request
