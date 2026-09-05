# infrastructure/webhooks/webhook_processor.py — WA-6 (§20 del prompt maestro)
"""
WebhookProcessor — la mitad "válida + persiste + crea inbox job" del
webhook (§20: "El webhook debe: validar, persistir mensaje, crear inbox
job, responder 200. Luego un worker: procesa intención..."). Procesar la
intención real es responsabilidad de `InboxWorker` (este mismo módulo) +
fases futuras (WA-7 Conversation Engine, WA-8 Intent Resolution) — no de
este processor.

**No reemplaza el webhook en vivo** (`webhook/whatsapp.py`, que sigue
procesando mensajes de forma síncrona vía `MessageRouter`/flows/ — el
camino real en producción hoy). Este módulo es la ruta nueva, en paralelo,
para cuando WA-9+ reemplace ese camino síncrono — mismo patrón "nuevo sin
cortar lo viejo" que domain/schema/bootstrap ya establecieron.

Reutiliza el parseo real y ya probado del webhook en vivo
(`models/message.py::IncomingMessage.from_webhook`) — no reinventa el
parseo del payload de Meta.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.whatsapp.entities.conversation import WhatsAppConversation
from domain.whatsapp.entities.identity import WhatsAppIdentity
from domain.whatsapp.entities.inbox_job import InboundMessageJob
from domain.whatsapp.entities.message import WhatsAppMessage
from domain.whatsapp.enums import MessageDirection
from domain.whatsapp.enums import MessageType as DomainMessageType
from domain.whatsapp.exceptions import ChannelNumberNotRegisteredError
from models.message import IncomingMessage, InteractiveType as LegacyInteractiveType
from models.message import MessageType as LegacyMessageType

# Mapeo del `MessageType` legacy que ya parsea `IncomingMessage.from_webhook`
# hacia el `MessageType` de dominio (WA-2, §15). No todo tipo legacy tiene
# equivalente 1:1 — `ORDER` (pedido nativo desde catálogo de WhatsApp) y
# `UNKNOWN` caen a TEXT como valor seguro; no existe un tipo de dominio
# "pedido de catálogo" todavía (candidato para cuando ese flujo se
# construya de verdad, no antes).
_LEGACY_TO_DOMAIN_TYPE = {
    LegacyMessageType.TEXT: DomainMessageType.TEXT,
    LegacyMessageType.IMAGE: DomainMessageType.IMAGE,
    LegacyMessageType.DOCUMENT: DomainMessageType.DOCUMENT,
    LegacyMessageType.LOCATION: DomainMessageType.LOCATION,
    LegacyMessageType.REACTION: DomainMessageType.REACTION,
}


def _resolve_domain_message_type(incoming: IncomingMessage) -> DomainMessageType:
    if incoming.type == LegacyMessageType.INTERACTIVE:
        if incoming.interactive_type == LegacyInteractiveType.BUTTON_REPLY:
            return DomainMessageType.BUTTON_REPLY
        if incoming.interactive_type == LegacyInteractiveType.LIST_REPLY:
            return DomainMessageType.LIST_REPLY
        return DomainMessageType.INTERACTIVE
    return _LEGACY_TO_DOMAIN_TYPE.get(incoming.type, DomainMessageType.TEXT)


@dataclass(frozen=True)
class WebhookProcessingResult:
    deduplicated: bool
    message_id: Optional[str]
    conversation_id: Optional[str]
    inbox_job_id: Optional[str]


class WebhookProcessor:
    """Persiste un `IncomingMessage` ya parseado como entidades de dominio
    (Identity/Conversation/Message) + crea su `InboundMessageJob`."""

    def __init__(self, root) -> None:
        self._root = root

    def process(self, incoming: IncomingMessage) -> WebhookProcessingResult:
        # Idempotencia técnica (§19): dedupe por provider_message_id —
        # UNIQUE en `whatsapp_messages` (migración 243) es la garantía de
        # esquema; esta consulta evita incluso intentar el INSERT.
        existing = self._root.messages.get_by_provider_message_id(incoming.message_id)
        if existing is not None:
            return WebhookProcessingResult(
                deduplicated=True, message_id=existing.id, conversation_id=None, inbox_job_id=None
            )

        channel_number = self._root.numbers.get_by_external_id(incoming.phone_number_id)
        if channel_number is None:
            raise ChannelNumberNotRegisteredError(
                f"phone_number_id={incoming.phone_number_id!r} no está registrado en "
                "whatsapp_channel_numbers — dar de alta el número (Accounts/Numbers, "
                "administración) antes de poder procesar mensajes para él."
            )

        identity = self._root.identities.get_by_wa_id(incoming.from_number)
        if identity is None:
            identity = WhatsAppIdentity.create(wa_id=incoming.from_number, raw_phone=incoming.from_number)
        else:
            identity.touch()
        self._root.identities.save(identity)

        conversation = self._root.conversations.get_open_for_identity(identity.id, channel_number.id)
        if conversation is None:
            conversation = WhatsAppConversation.open(
                identity_id=identity.id,
                channel_number_id=channel_number.id,
                branch_id=channel_number.branch_id,
            )
        conversation.record_inbound_message()
        self._root.conversations.save(conversation)

        message = WhatsAppMessage.create(
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            message_type=_resolve_domain_message_type(incoming),
            provider_message_id=incoming.message_id,
        )
        self._root.messages.save(message)

        job = InboundMessageJob.create(message_id=message.id)
        self._root.inbox.save(job)

        return WebhookProcessingResult(
            deduplicated=False,
            message_id=message.id,
            conversation_id=conversation.id,
            inbox_job_id=job.id,
        )
