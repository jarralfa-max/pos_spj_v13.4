# application/notification_service.py — WA-18 (§21-22 del prompt maestro)
"""
NotificationService — el reemplazo, dentro de la arquitectura nueva, de
`router/notify_router.py` (legacy, sigue vivo y sin tocar — mismo criterio
de "paralelo, no conectado todavía" que cada fase anterior). Cubre las
MISMAS 4 notificaciones de negocio (pedido listo / anticipo requerido /
cotización lista / mensaje libre) que el legacy, pero encolando vía
`OutboundMessageService` (WA-17) en vez de llamar `send_text` directo —
cierra el gap que WA-0/WA-3 documentaron para el camino ERP→WhatsApp
específicamente.

Cada notificación de negocio usa un `operation_id` determinístico
(`f"{tipo}:{folio}:{phone}"`) — un reintento del LLAMADOR (el ERP, vía
`core/integrations/whatsapp_client.py` o su reemplazo futuro) para la
MISMA notificación no encola un mensaje duplicado (`whatsapp_outbox.
operation_id` es `UNIQUE`, WA-3). Después de encolar, intenta un despacho
inmediato (`OutboundDispatcher.dispatch_now`, WA-17) — el llamador
recibe una señal real de éxito/fallo, no solo "quedó en cola", mientras la
garantía de entrega eventual (reintento/backoff) sigue cubierta si el
intento inmediato falla.
"""
from __future__ import annotations

from domain.whatsapp.entities.outbox_message import OutboxMessage


class NotificationService:
    def __init__(self, root) -> None:
        self._root = root

    async def _enqueue_and_attempt(self, *, phone: str, body: str, operation_id: str) -> OutboxMessage:
        message = self._root.outbound_message_service.enqueue_text(
            destination_phone=phone, body=body, operation_id=operation_id,
        )
        return await self._root.outbound_dispatcher.dispatch_now(message.id)

    async def notify_order_ready(self, *, phone: str, folio: str, branch_name: str = "") -> OutboxMessage:
        suffix = f" en {branch_name}" if branch_name else ""
        body = f"✅ ¡Tu pedido *{folio}* está listo para recoger{suffix}! 🛍️"
        return await self._enqueue_and_attempt(phone=phone, body=body, operation_id=f"order_ready:{folio}:{phone}")

    async def notify_advance_required(self, *, phone: str, folio: str, amount: float) -> OutboxMessage:
        body = (
            f"💳 Tu pedido *{folio}* requiere un anticipo de *${amount:.2f}*.\n"
            "Responde con el método de pago para continuar."
        )
        return await self._enqueue_and_attempt(
            phone=phone, body=body, operation_id=f"advance_required:{folio}:{phone}",
        )

    async def notify_quote_ready(self, *, phone: str, folio: str, total: float) -> OutboxMessage:
        body = (
            f"📋 Tu cotización *{folio}* está lista.\n"
            f"Total estimado: *${total:.2f}*\n"
            "Vigencia: 7 días. ¿Deseas confirmar el pedido?"
        )
        return await self._enqueue_and_attempt(phone=phone, body=body, operation_id=f"quote_ready:{folio}:{phone}")

    async def send_custom(self, *, phone: str, message: str) -> OutboxMessage:
        # Sin operation_id determinístico — un mensaje libre no tiene una
        # clave de negocio propia que lo identifique (a diferencia de los
        # tres anteriores, atados a un folio); cada llamada encola una
        # entrada nueva, mismo comportamiento que el legacy `/api/notify/send`.
        message_out = self._root.outbound_message_service.enqueue_text(destination_phone=phone, body=message)
        return await self._root.outbound_dispatcher.dispatch_now(message_out.id)
