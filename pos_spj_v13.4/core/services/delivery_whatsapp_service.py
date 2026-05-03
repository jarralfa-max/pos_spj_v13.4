from __future__ import annotations

import logging
from typing import Dict, Iterable

from core.integrations.whatsapp_client import WhatsAppClient

logger = logging.getLogger("spj.services.delivery_whatsapp")


class DeliveryWhatsAppService:
    STATUS_MESSAGES = {
        "pedido_recibido": "✅ Recibimos tu pedido {folio}. Lo estamos validando.",
        "preparacion": "👩‍🍳 Tu pedido {folio} está en preparación.",
        "en_ruta": "🛵 Tu pedido {folio} va en ruta.",
        "entregado": "🎉 Tu pedido {folio} fue entregado. ¡Gracias!",
        "cancelado": "❌ Tu pedido {folio} fue cancelado.",
    }

    def __init__(self, client: WhatsAppClient | None = None):
        self.client = client or WhatsAppClient()

    def notify_status(self, phone: str, folio: str, status: str) -> bool:
        if not phone:
            return False
        msg_template = self.STATUS_MESSAGES.get(status)
        if not msg_template:
            return False
        try:
            return bool(self.client.enviar_mensaje(phone, msg_template.format(folio=folio or "")))
        except Exception as exc:
            logger.warning("notify_status failed (%s): %s", status, exc)
            return False

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
