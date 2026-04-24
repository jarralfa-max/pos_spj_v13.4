from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from repositories.delivery_repository import DeliveryRepository
from core.services.delivery_whatsapp_service import DeliveryWhatsAppService
from core.services.geocoding_service import GeocodingService

logger = logging.getLogger("spj.services.delivery")


class DeliveryService:
    def __init__(
        self,
        db,
        repository: Optional[DeliveryRepository] = None,
        whatsapp_service: Optional[DeliveryWhatsAppService] = None,
        geocoding_service: Optional[GeocodingService] = None,
    ):
        self.db = db
        self.repository = repository or DeliveryRepository(db)
        self.whatsapp_service = whatsapp_service or DeliveryWhatsAppService()
        self.geocoding_service = geocoding_service or GeocodingService()

    def list_orders(self, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        self.pull_orders_from_whatsapp()
        return self.repository.list_orders(estado=estado)

    def create_order(self, data: Dict[str, Any], usuario: str = "sistema") -> int:
        direccion = (data.get("direccion") or "").strip()
        if not direccion:
            raise ValueError("No se puede crear pedido sin dirección válida")

        coords = data.get("coords") or self.geocoding_service.geocode(direccion)
        if coords:
            data["lat"] = coords.get("lat")
            data["lng"] = coords.get("lng")
        else:
            # fallback manual: permite guardar pero sin bloquear flujo
            data["lat"] = data.get("lat")
            data["lng"] = data.get("lng")

        data["usuario"] = usuario
        order_id = self.repository.create_order(data)
        self._publish("pedido_delivery_creado", {"order_id": order_id})
        self._publish("pedido_whatsapp_recibido", {"order_id": order_id, "canal": "whatsapp"})

        order = self.repository.get_order(order_id) or {}
        self._safe_wa_notify(order, "pedido_recibido")
        return order_id

    def update_status(self, order_id: int, status: str, usuario: str, responsable: str = "") -> None:
        if status == "entregado" and not responsable:
            raise ValueError("No se puede entregar sin responsable")

        self.repository.update_status(order_id, status, usuario=usuario, responsable=responsable)
        order = self.repository.get_order(order_id) or {}

        if status == "cancelado":
            self._release_stock(order_id)
        if status == "en_ruta":
            self._publish("pedido_en_ruta", {"order_id": order_id})
        if status == "entregado":
            self._publish("pedido_entregado", {"order_id": order_id, "responsable": responsable})

        self._safe_wa_notify(order, status)
        wa_id = order.get("whatsapp_order_id")
        self.whatsapp_service.sync_status(str(wa_id or ""), status)

    def autocomplete_address(self, query: str):
        return self.geocoding_service.autocomplete(query)

    def pull_orders_from_whatsapp(self) -> None:
        for item in self.whatsapp_service.pull_orders():
            try:
                oid = self.repository.upsert_order_from_whatsapp(item)
                self._publish("pedido_whatsapp_recibido", {"order_id": oid, "payload": item})
            except Exception as exc:
                logger.debug("pull_orders_from_whatsapp error: %s", exc)

    def _safe_wa_notify(self, order: Dict[str, Any], status: str) -> None:
        ok = self.whatsapp_service.notify_status(
            phone=order.get("cliente_tel", ""),
            folio=order.get("folio") or str(order.get("id") or ""),
            status=status,
        )
        self._publish("notificacion_whatsapp_enviada", {
            "order_id": order.get("id"), "status": status, "ok": bool(ok)
        })

    def _release_stock(self, order_id: int) -> None:
        self._publish("stock_liberar_solicitado", {"order_id": order_id})

    def _publish(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            from core.events.event_bus import get_bus

            get_bus().publish(event, payload)
        except Exception:
            pass
