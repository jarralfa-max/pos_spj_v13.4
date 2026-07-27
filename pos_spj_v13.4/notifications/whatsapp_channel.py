"""WhatsApp notification channel — delegates to DeliveryWhatsAppService."""
from __future__ import annotations

import logging
from typing import Optional

from notifications.base import NotificationChannel, NotificationPayload

logger = logging.getLogger("spj.notifications.whatsapp")


class WhatsAppNotificationChannel(NotificationChannel):
    """Sends WhatsApp messages via DeliveryWhatsAppService.

    Parameters
    ----------
    wa_service:
        Optional DeliveryWhatsAppService instance.  If None, the channel
        tries to instantiate the default service on first send.
    """

    def __init__(self, wa_service=None) -> None:
        self._wa = wa_service
        self._init_failed = False

    def _get_service(self):
        if self._wa is not None:
            return self._wa
        if self._init_failed:
            return None
        try:
            from core.services.delivery_whatsapp_service import DeliveryWhatsAppService
            self._wa = DeliveryWhatsAppService()
            return self._wa
        except Exception as exc:
            logger.warning("WhatsAppChannel: service init failed: %s", exc)
            self._init_failed = True
            return None

    def is_available(self) -> bool:
        return self._get_service() is not None

    def send(self, payload: NotificationPayload) -> bool:
        wa = self._get_service()
        if wa is None:
            return False
        phone = (payload.cliente_tel or "").strip()
        if not phone:
            return False
        try:
            if hasattr(wa, "notify_from_event"):
                ok = wa.notify_from_event({
                    "order_id": payload.order_id,
                    "canal": "whatsapp",
                    "template": payload.event_type,
                    "params": payload.metadata or {"message": payload.body},
                    "cliente_tel": phone,
                    "folio": payload.folio or str(payload.order_id or ""),
                })
            else:
                ok = wa.notify_status(phone=phone, folio=payload.folio or str(payload.order_id or ""), status=payload.event_type)
            logger.debug("WhatsAppChannel: sent event=%s phone=%s", payload.event_type, phone[:6])
            return bool(ok)
        except Exception as exc:
            logger.warning("WhatsAppChannel send failed: %s", exc)
            return False
