# infrastructure/webhooks/outbound_dispatcher.py — WA-17 (§21-22 del prompt maestro)
"""
OutboundDispatcher — drena `whatsapp_outbox` y despacha cada mensaje vía
`ProviderGateway` (WA-5). Mismo patrón "claim -> intentar -> completar/
reintentar/dead-letter" que `InboxWorker` (WA-6), espejado para el sentido
saliente — cierra el gap que WA-0/WA-3 documentaron ("el microservicio
envía síncrono, sin outbox persistido").

Vive en `infrastructure/webhooks/` junto a `InboxWorker`, no en
`application/`, por el mismo motivo que ese: es un mecanismo de despacho
sobre un puerto de infraestructura (`ProviderGateway`), no una decisión de
negocio. Tampoco es un scheduler — `run_once()` es invocable por un cron,
un endpoint admin, o un loop real; esa decisión de despliegue queda fuera
de esta fase (mismo alcance que `InboxWorker`).
"""
from __future__ import annotations

import logging

from domain.whatsapp.entities.outbox_message import OutboxMessage

logger = logging.getLogger("wa.outbound_dispatcher")


class OutboundDispatcher:
    def __init__(self, root) -> None:
        self._root = root

    async def run_once(self, *, limit: int = 10) -> int:
        """Reclama hasta `limit` mensajes pendientes-y-vencidos (PENDING,
        `next_retry_at` cumplido) y los despacha. Retorna cuántos se
        reclamaron (no cuántos tuvieron éxito — ver logs)."""
        outbox = self._root.outbox
        messages = outbox.claim_due(limit=limit)
        for message in messages:
            await self._dispatch_one(message)
        return len(messages)

    async def dispatch_now(self, message_id: str) -> OutboxMessage:
        """Despacha UN mensaje específico de inmediato (WA-18: un llamador
        síncrono como `/api/notify/*` quiere saber si el envío tuvo éxito
        ahora mismo, no solo que quedó en cola). Si el mensaje ya es
        terminal o no está vencido (`next_retry_at` futuro tras un fallo
        previo), no hace nada — la garantía de entrega eventual sigue
        siendo `run_once()` corriendo periódicamente, esto es solo un
        intento adelantado, no un camino de envío distinto."""
        outbox = self._root.outbox
        message = outbox.get_by_id(message_id)
        if message is None:
            raise ValueError(f"OutboxMessage {message_id} no encontrado")
        if not message.is_due():
            return message
        message.claim()
        outbox.save(message)
        await self._dispatch_one(message)
        return message

    async def _dispatch_one(self, message: OutboxMessage) -> None:
        outbox = self._root.outbox
        gateway = self._root.provider_gateway
        try:
            payload = message.payload
            if payload["kind"] == "text":
                await gateway.send_text(to=message.destination_phone, body=payload["body"])
            elif payload["kind"] == "template":
                await gateway.send_template(
                    to=message.destination_phone, template_name=payload["template_name"],
                    language=payload.get("language", "es_MX"), parameters=payload.get("parameters", {}),
                )
            else:
                raise ValueError(f"Tipo de payload de outbox desconocido: {payload['kind']!r}")
        except Exception as exc:
            message.mark_failed(str(exc))
            logger.warning(
                "OutboxMessage %s falló (intento %d): %s", message.id, message.attempts, exc
            )
            outbox.save(message)
            return

        message.mark_sent()
        outbox.save(message)
