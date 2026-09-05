# application/outbound_message_service.py — WA-17 (§21-22 del prompt maestro)
"""
OutboundMessageService — el punto único para poner un mensaje saliente en
`whatsapp_outbox`. Idempotente sobre `operation_id` cuando el llamador lo
provee: `whatsapp_outbox.operation_id` es `UNIQUE` (WA-3) — dos intentos de
encolar la MISMA operación de negocio (p. ej. "notificar pedido listo
F-001" reintentado por el llamador) devuelven el mismo `OutboxMessage`, no
uno duplicado.

No decide envío directo — eso es `OutboundDispatcher.run_once()`. Este
servicio solo escribe la cola.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from domain.whatsapp.entities.outbox_message import OutboxMessage


class OutboundMessageService:
    def __init__(self, root) -> None:
        self._root = root

    def enqueue_text(
        self, *, destination_phone: str, body: str, conversation_id: Optional[str] = None,
        channel_number_id: Optional[str] = None, operation_id: Optional[str] = None,
    ) -> OutboxMessage:
        if operation_id:
            existing = self._root.outbox.get_by_operation_id(operation_id)
            if existing is not None:
                return existing

        message = OutboxMessage.enqueue_text(
            destination_phone=destination_phone, body=body, conversation_id=conversation_id,
            channel_number_id=channel_number_id, operation_id=operation_id,
        )
        self._root.outbox.save(message)
        return message

    def enqueue_template(
        self, *, destination_phone: str, template_name: str, language: str = "es_MX",
        parameters: Optional[Dict[str, Any]] = None, conversation_id: Optional[str] = None,
        channel_number_id: Optional[str] = None, operation_id: Optional[str] = None,
    ) -> OutboxMessage:
        if operation_id:
            existing = self._root.outbox.get_by_operation_id(operation_id)
            if existing is not None:
                return existing

        message = OutboxMessage.enqueue_template(
            destination_phone=destination_phone, template_name=template_name, language=language,
            parameters=parameters, conversation_id=conversation_id, channel_number_id=channel_number_id,
            operation_id=operation_id,
        )
        self._root.outbox.save(message)
        return message
