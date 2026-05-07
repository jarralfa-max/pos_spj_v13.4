"""DeliveryNotificationService — routes notifications to the correct channel(s).

Usage:
    svc = DeliveryNotificationService()
    svc.notify(NotificationPayload(
        event_type="delivery_new",
        title="Nuevo pedido",
        body="Pedido #42 recibido",
        channel="all",
        priority="normal",
    ))

Channel routing rules:
  "all"      → sound + toast + (desktop if available)
  "sound"    → sound only
  "toast"    → toast only
  "whatsapp" → whatsapp only
  "desktop"  → desktop only
  "silent"   → no channels (audit-only)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from notifications.base import NotificationChannel, NotificationPayload

logger = logging.getLogger("spj.notifications.service")


class DeliveryNotificationService:
    """Routes notification payloads to registered channels.

    Thread-safety notes:
    - Sound and desktop channels must only be called from the Qt main thread.
      They use QTimer.singleShot internally for safe dispatch.
    - WhatsApp channel is thread-safe (HTTP call).
    - Toast channel dispatches to main thread via QTimer.singleShot.
    """

    def __init__(self, channels: Optional[List[NotificationChannel]] = None) -> None:
        self._channels: List[NotificationChannel] = channels if channels is not None else []

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    # ── Public interface ──────────────────────────────────────────────────────

    def notify(self, payload: NotificationPayload) -> None:
        """Route payload to matching channels. Never raises."""
        target = (payload.channel or "all").lower()
        for ch in self._channels:
            ch_name = type(ch).__name__.lower()
            if not self._should_send(target, ch_name):
                continue
            if not ch.is_available():
                continue
            try:
                ch.send(payload)
            except Exception as exc:
                logger.warning("Channel %s send error: %s", ch_name, exc)

    def notify_delivery_created(self, order_id: int, folio: str, sucursal_id: int = 1) -> None:
        self.notify(NotificationPayload(
            event_type="delivery_created",
            title="Nuevo pedido delivery",
            body=f"Pedido #{folio or order_id} recibido",
            channel="all",
            order_id=order_id,
            folio=folio,
            priority="normal",
            sucursal_id=sucursal_id,
        ))

    def notify_delivery_preparing(self, order_id: int, folio: str, sucursal_id: int = 1) -> None:
        self.notify(NotificationPayload(
            event_type="delivery_preparing",
            title="Pedido en preparación",
            body=f"Pedido #{folio or order_id} en cocina",
            channel="sound",
            order_id=order_id,
            folio=folio,
            priority="normal",
            sucursal_id=sucursal_id,
        ))

    def notify_delivery_delivered(self, order_id: int, folio: str, sucursal_id: int = 1) -> None:
        self.notify(NotificationPayload(
            event_type="delivery_delivered",
            title="Pedido entregado",
            body=f"Pedido #{folio or order_id} entregado",
            channel="all",
            order_id=order_id,
            folio=folio,
            priority="normal",
            sucursal_id=sucursal_id,
        ))

    def notify_driver_assigned(
        self, order_id: int, folio: str, driver_nombre: str,
        cliente_tel: str = "", sucursal_id: int = 1,
    ) -> None:
        self.notify(NotificationPayload(
            event_type="driver_assigned",
            title="Repartidor asignado",
            body=f"Pedido #{folio}: {driver_nombre} asignado",
            channel="whatsapp",
            order_id=order_id,
            folio=folio,
            cliente_tel=cliente_tel,
            priority="normal",
            sucursal_id=sucursal_id,
        ))

    def notify_weight_adjusted(
        self, order_id: int, folio: str, new_total: float,
        cliente_tel: str = "", sucursal_id: int = 1,
    ) -> None:
        self.notify(NotificationPayload(
            event_type="weight_adjusted",
            title="Peso ajustado",
            body=f"Pedido #{folio}: total actualizado a ${new_total:.2f}",
            channel="all",
            order_id=order_id,
            folio=folio,
            cliente_tel=cliente_tel,
            priority="normal",
            sucursal_id=sucursal_id,
            metadata={"new_total": new_total},
        ))

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _should_send(target: str, channel_name: str) -> bool:
        if target == "all":
            return "whatsapp" not in channel_name   # WA needs explicit routing
        if target == "silent":
            return False
        return target in channel_name


def build_default_service() -> DeliveryNotificationService:
    """Build a DeliveryNotificationService with all available channels.

    Called once during app init (AppContainer or wiring.py).
    """
    from notifications.sound_channel import SoundNotificationChannel
    from notifications.toast_channel import ToastNotificationChannel
    from notifications.desktop_channel import DesktopNotificationChannel
    from notifications.whatsapp_channel import WhatsAppNotificationChannel

    svc = DeliveryNotificationService()
    svc.add_channel(SoundNotificationChannel())
    svc.add_channel(ToastNotificationChannel())
    svc.add_channel(DesktopNotificationChannel())
    svc.add_channel(WhatsAppNotificationChannel())
    logger.debug("DeliveryNotificationService built with 4 channels")
    return svc
