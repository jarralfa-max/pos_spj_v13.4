from __future__ import annotations

import logging
from typing import Any

from core.integrations.whatsapp_client import WhatsAppClient

logger = logging.getLogger("spj.delivery.whatsapp_notifier")


class WhatsAppDeliveryNotifier:
    """DeliveryNotifierPort implementation backed by WhatsAppClient.

    Message templates live here so application use cases emit notification
    requests instead of building long WhatsApp strings inline.
    """

    STATUS_TEMPLATES: dict[str, str] = {
        "pedido_recibido": "✅ Recibimos tu pedido {folio}. Lo estamos validando.",
        "pending": "✅ Tu pedido {folio} quedó registrado.",
        "preparing": "👩‍🍳 Tu pedido {folio} está en preparación.",
        "in_transit": "🛵 Tu pedido {folio} va en ruta.",
        "delivered": "🎉 Tu pedido {folio} fue entregado. ¡Gracias!",
        "cancelled": "❌ Tu pedido {folio} fue cancelado.",
        # Spanish compat aliases — removed after all instances upgrade
        "pendiente": "✅ Tu pedido {folio} quedó registrado.",
        "preparacion": "👩‍🍳 Tu pedido {folio} está en preparación.",
        "en_ruta": "🛵 Tu pedido {folio} va en ruta.",
        "entregado": "🎉 Tu pedido {folio} fue entregado. ¡Gracias!",
        "cancelado": "❌ Tu pedido {folio} fue cancelado.",
    }

    def __init__(self, client: WhatsAppClient | None = None) -> None:
        self.client = client or WhatsAppClient()

    def notify_status(self, *, phone: str, folio: str, status: str) -> bool:
        template = self.STATUS_TEMPLATES.get((status or "").strip().lower())
        if not template:
            return False
        return self._send(phone, template.format(folio=folio or ""), template=status)

    def notify_adjustment_required(
        self,
        *,
        phone: str,
        folio: str,
        item_name: str = "Producto",
        requested_qty: float = 0,
        prepared_qty: float = 0,
        unit: str = "",
        new_subtotal: float = 0,
        diff_qty: float | None = None,
    ) -> bool:
        diff = prepared_qty - requested_qty if diff_qty is None else float(diff_qty)
        sign = "+" if diff >= 0 else ""
        message = (
            f"⚖️ *Ajuste de tu pedido {folio}*\n\n"
            f"Producto: {item_name}\n"
            f"Solicitado: {requested_qty:.3g} {unit}\n"
            f"Preparado: {prepared_qty:.3g} {unit} ({sign}{diff:.3g} {unit})\n"
            f"Nuevo subtotal: ${new_subtotal:,.2f}\n\n"
            "Responde *ACEPTAR AJUSTE* para autorizarlo o *RECHAZAR AJUSTE* para mantener el pedido sin ese cambio."
        )
        return self._send(phone, message, template="adjustment_required")

    def notify_weight_adjustment(
        self,
        *,
        phone: str,
        folio: str,
        requested_qty: float,
        prepared_qty: float,
        unit: str = "",
        new_total: float = 0,
        payment_url: str = "",
    ) -> bool:
        diff = prepared_qty - requested_qty
        sign = "+" if diff >= 0 else ""
        message = (
            f"📦 Actualización pedido #{folio}\n"
            f"Peso solicitado: {requested_qty:.3g} {unit}\n"
            f"Peso real: {prepared_qty:.3g} {unit} ({sign}{diff:.3g} {unit})\n"
            f"Total: ${new_total:,.2f}"
        )
        if payment_url:
            message += f"\nPago: {payment_url}"
        message += "\n🛵 ¡Pronto en camino!"
        return self._send(phone, message, template="weight_adjustment")

    def notify_out_for_delivery(self, *, phone: str, folio: str, driver_name: str = "", eta: str = "") -> bool:
        details = []
        if driver_name:
            details.append(f"Repartidor: {driver_name}")
        if eta:
            details.append(f"ETA: {eta}")
        suffix = "\n" + "\n".join(details) if details else ""
        return self._send(phone, f"🛵 Tu pedido {folio} va en ruta.{suffix}", template="out_for_delivery")

    def notify_delivered(self, *, phone: str, folio: str) -> bool:
        return self._send(phone, f"🎉 Tu pedido {folio} fue entregado. ¡Gracias!", template="delivered")

    def notify_from_event(self, payload: dict[str, Any]) -> bool:
        template = str(payload.get("template") or "").strip().lower()
        params = payload.get("params") or {}
        phone = str(payload.get("cliente_tel") or params.get("cliente_tel") or "")
        folio = str(payload.get("folio") or params.get("folio") or payload.get("order_id") or "")

        if template == "adjustment_required":
            return self.notify_adjustment_required(
                phone=phone,
                folio=folio,
                item_name=str(params.get("item_name") or "Producto"),
                requested_qty=float(params.get("requested_qty") or 0),
                prepared_qty=float(params.get("prepared_qty") or 0),
                unit=str(params.get("unit") or ""),
                new_subtotal=float(params.get("new_subtotal") or 0),
                diff_qty=float(params.get("diff_qty") or 0),
            )
        if template in {"weight_adjustment", "item_weight_adjusted"}:
            return self.notify_weight_adjustment(
                phone=phone,
                folio=folio,
                requested_qty=float(params.get("requested_qty") or 0),
                prepared_qty=float(params.get("prepared_qty") or 0),
                unit=str(params.get("unit") or ""),
                new_total=float(params.get("new_total") or params.get("total") or 0),
                payment_url=str(params.get("payment_url") or ""),
            )
        if template in {"en_ruta", "out_for_delivery"}:
            return self.notify_out_for_delivery(
                phone=phone,
                folio=folio,
                driver_name=str(params.get("driver_name") or params.get("driver_nombre") or ""),
                eta=str(params.get("eta") or ""),
            )
        if template in {"entregado", "delivered"}:
            return self.notify_delivered(phone=phone, folio=folio)
        return self.notify_status(phone=phone, folio=folio, status=template)

    def _send(self, phone: str, message: str, *, template: str) -> bool:
        if not phone:
            return False
        try:
            ok = bool(self.client.enviar_mensaje(phone, message))
            logger.info("whatsapp delivery template=%s phone=%s ok=%s", template, phone[-4:], ok)
            return ok
        except Exception as exc:
            logger.warning("whatsapp delivery template=%s failed: %s", template, exc)
            return False
