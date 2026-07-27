from __future__ import annotations

import logging
from typing import Dict, Iterable

from core.delivery.infrastructure.whatsapp_delivery_notifier import WhatsAppDeliveryNotifier
from core.integrations.whatsapp_client import WhatsAppClient

logger = logging.getLogger("spj.services.delivery_whatsapp")


class DeliveryWhatsAppService:
    """Legacy-compatible façade over the centralized WhatsApp delivery notifier."""

    STATUS_MESSAGES = WhatsAppDeliveryNotifier.STATUS_TEMPLATES

    def __init__(self, client: WhatsAppClient | None = None, notifier: WhatsAppDeliveryNotifier | None = None):
        self.client = client or WhatsAppClient()
        self.notifier = notifier or WhatsAppDeliveryNotifier(self.client)

    def notify_status(self, phone: str, folio: str, status: str) -> bool:
        return self.notifier.notify_status(phone=phone, folio=folio, status=status)

    def notify_adjustment_required(self, **kwargs) -> bool:
        return self.notifier.notify_adjustment_required(**kwargs)

    def notify_weight_adjustment(
        self,
        phone: str,
        folio: str,
        requested_qty: float,
        prepared_qty: float,
        unit: str,
        new_total: float,
        payment_url: str = "",
    ) -> bool:
        return self.notifier.notify_weight_adjustment(
            phone=phone,
            folio=folio,
            requested_qty=requested_qty,
            prepared_qty=prepared_qty,
            unit=unit,
            new_total=new_total,
            payment_url=payment_url,
        )

    def notify_out_for_delivery(self, *, phone: str, folio: str, driver_name: str = "", eta: str = "") -> bool:
        return self.notifier.notify_out_for_delivery(phone=phone, folio=folio, driver_name=driver_name, eta=eta)

    def notify_delivered(self, *, phone: str, folio: str) -> bool:
        return self.notifier.notify_delivered(phone=phone, folio=folio)

    def notify_from_event(self, payload: dict) -> bool:
        return self.notifier.notify_from_event(payload)

    def pull_orders(self) -> Iterable[Dict]:
        try:
            payload = self.client._get("/api/delivery/orders/pending") or {}
            items = payload.get("orders") if isinstance(payload, dict) else None
            return items or []
        except Exception as exc:
            logger.debug("pull_orders: %s", exc)
            return []

    def sync_status(self, whatsapp_order_id: str, status: str) -> bool:
        if not whatsapp_order_id:
            return False
        try:
            payload = {"whatsapp_order_id": whatsapp_order_id, "status": status}
            result = self.client._post("/api/delivery/orders/status", payload) or {}
            return bool(result.get("ok", False))
        except Exception as exc:
            logger.debug("sync_status: %s", exc)
            return False
