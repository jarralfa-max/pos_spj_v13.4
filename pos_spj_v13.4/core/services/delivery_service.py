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
        # WA pull is decoupled from the read path to avoid blocking the UI thread.
        # Call pull_orders_from_whatsapp() separately (e.g., from a background timer).
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
            data["lat"] = data.get("lat")
            data["lng"] = data.get("lng")

        data["usuario"] = usuario
        order_id = self.repository.create_order(data)
        self._publish("pedido_delivery_creado", {"order_id": order_id})
        self._publish("pedido_whatsapp_recibido", {"order_id": order_id, "canal": "whatsapp"})

        # Reserve inventory for items that have a product_id (soft-lock)
        items = data.get("items") or []
        if items:
            self._publish(
                "DELIVERY_ORDER_RESERVED",
                {
                    "order_id": order_id,
                    "operation_id": str(order_id),
                    "items": items,
                    "branch_id": data.get("sucursal_id", 1),
                    "db": self.db,
                },
            )

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

    def adjust_item_weight(
        self,
        order_id: int,
        item_id: int,
        prepared_qty: float,
        prepared_by: str,
        adjustment_reason: str = "",
        unit: str = "kg",
    ) -> Dict[str, Any]:
        """Record the real prepared weight for a variable-weight item.

        Publishes DELIVERY_ITEM_WEIGHT_ADJUSTED which triggers:
          - DeliveryWeightAdjustmentHandler (recalculates total)
          - DeliveryWhatsAppNotificationHandler (notifies client)
          - DeliveryPaymentUpdateHandler (via DELIVERY_TOTAL_UPDATED)

        Returns {new_total, diff_qty, diff_pct, tolerance_exceeded}.
        """
        from core.services.reservation_service import ReservationService

        # Load current item data
        item_row = self.db.execute(
            "SELECT precio_unitario, cantidad, nombre FROM delivery_items WHERE id=?",
            (item_id,),
        ).fetchone()
        if not item_row:
            raise ValueError(f"delivery_items.id={item_id} not found")

        unit_price   = float(item_row[0] or 0)
        requested_qty = float(item_row[1] or prepared_qty)
        item_name    = item_row[2] or ""

        adj = ReservationService.compute_adjustment(requested_qty, prepared_qty, unit_price)

        order = self.repository.get_order(order_id) or {}
        folio = order.get("folio") or str(order_id)

        self._publish(
            "DELIVERY_ITEM_WEIGHT_ADJUSTED",
            {
                "order_id": order_id,
                "item_id": item_id,
                "item_name": item_name,
                "requested_qty": requested_qty,
                "prepared_qty": prepared_qty,
                "unit_price": unit_price,
                "unit": unit,
                "prepared_by": prepared_by,
                "adjustment_reason": adjustment_reason,
                "new_total": adj["new_subtotal"],   # updated by handler
                "folio": folio,
                "cliente_tel": order.get("cliente_tel", ""),
                "cliente_email": order.get("cliente_email", ""),
                "db": self.db,
            },
        )
        logger.info(
            "adjust_item_weight: order=%s item=%s requested=%.3f prepared=%.3f "
            "diff_pct=%.1f%% tolerance_exceeded=%s",
            order_id, item_id, requested_qty, prepared_qty,
            adj["diff_pct"], adj["tolerance_exceeded"],
        )
        return adj

    def get_order_items(self, order_id: int) -> List[Dict[str, Any]]:
        """Return delivery_items rows for an order."""
        try:
            rows = self.db.execute(
                """SELECT id, nombre, cantidad, precio_unitario, subtotal, unidad,
                          producto_id, requested_qty, prepared_qty, final_qty,
                          prepared_by, prepared_at, adjustment_reason, tolerance_exceeded
                   FROM delivery_items WHERE delivery_id=? ORDER BY id""",
                (order_id,),
            ).fetchall()
            cols = ["id", "nombre", "cantidad", "precio_unitario", "subtotal", "unidad",
                    "producto_id", "requested_qty", "prepared_qty", "final_qty",
                    "prepared_by", "prepared_at", "adjustment_reason", "tolerance_exceeded"]
            return [dict(zip(cols, r)) for r in rows]
        except Exception as exc:
            logger.debug("get_order_items error: %s", exc)
            return []

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
