from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from repositories.delivery_repository import DeliveryRepository
from core.services.delivery_whatsapp_service import DeliveryWhatsAppService
from core.services.geocoding_service import GeocodingService
from core.services.order_total_service import OrderTotalService

logger = logging.getLogger("spj.services.delivery")

ADJUSTMENT_PENDING = "pending_customer"
ADJUSTMENT_ACCEPTED = "accepted"
ADJUSTMENT_REJECTED = "rejected"
ADJUSTMENT_NONE = "none"


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
        self.order_total_service = OrderTotalService(db)
        self._ensure_adjustment_columns()

    def _ensure_adjustment_columns(self) -> None:
        """Asegura columnas de aprobación sin depender de que la migración ya haya corrido."""
        cols_items = [
            "pending_prepared_qty REAL",
            "pending_subtotal REAL",
            "adjustment_status TEXT DEFAULT 'none'",
            "adjustment_requested_at DATETIME",
            "adjustment_responded_at DATETIME",
            "adjustment_response TEXT",
            "adjustment_token TEXT",
            "tolerance_units REAL DEFAULT 0.2",
        ]
        cols_orders = [
            "adjustment_pending INTEGER DEFAULT 0",
            "adjustment_blocked_state TEXT DEFAULT ''",
        ]
        for col in cols_items:
            try:
                self.db.execute(f"ALTER TABLE delivery_items ADD COLUMN {col}")
            except Exception:
                pass
        for col in cols_orders:
            try:
                self.db.execute(f"ALTER TABLE delivery_orders ADD COLUMN {col}")
            except Exception:
                pass
        try:
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_items_adjustment_status ON delivery_items(adjustment_status, delivery_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_delivery_items_adjustment_token ON delivery_items(adjustment_token)")
            self.db.commit()
        except Exception:
            pass

    def list_orders(self, estado: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.repository.list_orders(estado=estado)

    def get_valid_actions(
        self,
        *,
        status: str,
        workflow_type: str = "",
        adjustment_pending: bool = False,
        scheduled_at: Optional[str] = None,
        delivery_type: str = "",
    ) -> List[Dict[str, str]]:
        """Return valid UI actions for an order context.

        Backend-facing contract in English so UI does not handcraft action rules.
        """
        base = {
            "pendiente": [
                {"icon": "👨‍🍳", "label": "Enviar a preparación", "key": "preparacion", "style": "primary"},
                {"icon": "✖", "label": "Cancelar pedido", "key": "cancelado", "style": "danger"},
                {"icon": "🔍", "label": "Ver detalle", "key": "ver_detalle", "style": "secondary"},
            ],
            "preparacion": [
                {"icon": "⚖️", "label": "Ajustar peso", "key": "ajustar_peso", "style": "warning"},
                {"icon": "🛵", "label": "Enviar a ruta", "key": "en_ruta", "style": "primary"},
                {"icon": "👤", "label": "Asignar repartidor", "key": "asignar", "style": "primary"},
                {"icon": "✖", "label": "Cancelar pedido", "key": "cancelado", "style": "danger"},
            ],
            "en_ruta": [
                {"icon": "✅", "label": "Marcar entregado", "key": "entregado", "style": "success"},
                {"icon": "📲", "label": "Notificar por WA", "key": "notificar_wa", "style": "secondary"},
            ],
            "entregado": [
                {"icon": "🖨️", "label": "Imprimir ticket", "key": "imprimir", "style": "secondary"},
            ],
            "cancelado": [
                {"icon": "♻️", "label": "Reactivar pedido", "key": "reactivar", "style": "warning"},
            ],
        }
        s = (status or "").strip().lower()
        wf = (workflow_type or "").strip().lower()
        actions = list(base.get(s, []))
        if wf == "counter":
            actions = [a for a in actions if a["key"] not in ("en_ruta", "asignar")]
            if s == "preparacion":
                actions.insert(1, {"icon": "✅", "label": "Marcar entregado", "key": "entregado", "style": "success"})
        if wf == "scheduled" and s in ("programado", "scheduled"):
            actions = [
                {"icon": "▶", "label": "Activar ahora", "key": "activar_programado", "style": "success"},
                {"icon": "🗓️", "label": "Reprogramar", "key": "reprogramar", "style": "warning"},
                {"icon": "📈", "label": "Ver forecast", "key": "ver_forecast", "style": "secondary"},
                {"icon": "✖", "label": "Cancelar pedido", "key": "cancelado", "style": "danger"},
            ]
        if adjustment_pending:
            actions = [a for a in actions if a["key"] not in ("en_ruta", "entregado")]
        return actions

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

        self._publish("DELIVERY_ORDER_CREATED", {
            "_event_type": "DELIVERY_ORDER_CREATED",
            "order_id": order_id,
            "folio": order.get("folio") or data.get("folio") or f"DEL-{order_id}",
            "direccion": data.get("direccion"),
            "total": data.get("total", 0),
            "sucursal_id": data.get("sucursal_id", 1),
            "usuario": usuario,
            "db": self.db,
        })
        return order_id

    def _has_pending_adjustment(self, order_id: int) -> bool:
        try:
            row = self.db.execute(
                """SELECT 1 FROM delivery_items
                   WHERE delivery_id=? AND adjustment_status=? LIMIT 1""",
                (order_id, ADJUSTMENT_PENDING),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    def update_status(self, order_id: int, status: str, usuario: str, responsable: str = "") -> None:
        self._validate_workflow_transition(order_id, status)

        if status == "entregado" and not responsable:
            raise ValueError("No se puede entregar sin responsable")

        if status in ("en_ruta", "entregado") and self._has_pending_adjustment(order_id):
            try:
                self.db.execute(
                    "UPDATE delivery_orders SET adjustment_pending=1, adjustment_blocked_state=? WHERE id=?",
                    (status, order_id),
                )
                self.db.commit()
            except Exception:
                pass
            raise ValueError(
                "No se puede cambiar de estado: hay un ajuste de peso/cantidad pendiente de aceptación del cliente."
            )

        self.repository.update_status(order_id, status, usuario=usuario, responsable=responsable)
        order = self.repository.get_order(order_id) or {}
        folio = order.get("folio") or f"DEL-{order_id}"
        sucursal_id = int(order.get("sucursal_id") or 1)
        cliente_tel = order.get("cliente_tel") or ""
        _base = {
            "_event_type": f"DELIVERY_ORDER_{status.upper()}",
            "order_id": order_id,
            "folio": folio,
            "usuario": usuario,
            "sucursal_id": sucursal_id,
            "total": order.get("total"),
            "db": self.db,
        }

        if status == "cancelado":
            self._release_stock(order_id)
            self._publish("DELIVERY_ORDER_CANCELLED", {**_base, "motivo": ""})
        if status == "preparacion":
            self._publish("DELIVERY_ORDER_PREPARING", _base)
        if status == "en_ruta":
            self._publish("pedido_en_ruta", {"order_id": order_id})
            self._publish("DELIVERY_OUT_FOR_DELIVERY", {
                **_base, "_event_type": "DELIVERY_OUT_FOR_DELIVERY",
                "driver_id": order.get("driver_id"),
                "cliente_tel": cliente_tel,
            })
        if status == "entregado":
            self._publish("pedido_entregado", {"order_id": order_id, "responsable": responsable})
            self._publish("DELIVERY_ORDER_DELIVERED", {
                **_base, "_event_type": "DELIVERY_ORDER_DELIVERED",
                "responsable": responsable,
                "driver_id": order.get("driver_id"),
            })
            items = self.get_order_items(order_id)
            self._publish("INVENTORY_COMMIT_REQUIRED", {
                "order_id": order_id,
                "operation_id": str(order_id),
                "items": items,
                "sucursal_id": sucursal_id,
                "branch_id": sucursal_id,
                "db": self.db,
            })

        self._safe_wa_notify(order, status)
        wa_id = order.get("whatsapp_order_id")
        self.whatsapp_service.sync_status(str(wa_id or ""), status)

    def activate_scheduled_order(self, order_id: int, usuario: str = "sistema") -> Dict[str, Any]:
        """Activate a scheduled order into its operational flow.

        - scheduled + pickup/sucursal -> counter workflow
        - scheduled + domicilio/home_delivery -> delivery workflow
        - status changes from programado/scheduled to pendiente
        """
        order = self.repository.get_order(order_id) or {}
        if not order:
            raise ValueError("Pedido no encontrado.")

        current_status = (order.get("estado") or "").strip().lower()
        if current_status not in ("programado", "scheduled"):
            raise ValueError("Solo se pueden activar pedidos en estado programado.")

        delivery_type = (order.get("delivery_type") or order.get("tipo_entrega") or "").strip().lower()
        target_workflow = "counter" if delivery_type in ("pickup", "sucursal") else "delivery"

        self.db.execute(
            """
            UPDATE delivery_orders
            SET workflow_type=?, estado='pendiente', fecha_actualizacion=datetime('now')
            WHERE id=?
            """,
            (target_workflow, order_id),
        )
        try:
            self.db.execute(
                "UPDATE ventas SET workflow_type=?, estado='pendiente' WHERE id=?",
                (target_workflow, order.get("venta_id")),
            )
        except Exception:
            pass
        self.db.commit()

        self._publish("WHATSAPP_SCHEDULED_ORDER_ACTIVATED", {
            "order_id": order_id,
            "workflow_type": target_workflow,
            "usuario": usuario,
            "sucursal_id": int(order.get("sucursal_id") or 1),
            "db": self.db,
        })
        return {"order_id": order_id, "workflow_type": target_workflow, "status": "pending"}

    def _validate_workflow_transition(self, order_id: int, target_status: str) -> None:
        order = self.repository.get_order(order_id) or {}
        workflow_type = (order.get("workflow_type") or "").strip().lower()
        delivery_type = (order.get("delivery_type") or "").strip().lower()
        scheduled_at = order.get("scheduled_at")

        if not workflow_type:
            if scheduled_at:
                workflow_type = "scheduled"
            elif delivery_type in ("pickup", "sucursal"):
                workflow_type = "counter"
            else:
                workflow_type = "delivery"

        if workflow_type == "scheduled" and target_status in ("preparacion", "en_ruta", "entregado"):
            raise ValueError("Pedido programado: primero debe activarse antes de pasar a flujo operativo.")

        if workflow_type == "counter" and target_status == "en_ruta":
            raise ValueError("Flujo mostrador no permite estado 'en_ruta'.")

    def _recalculate_order_total(self, order_id: int) -> float:
        return self.order_total_service.recalculate_order_total(order_id)

    def _sync_venta_total(self, order_id: int, new_total: float) -> None:
        try:
            order = self.repository.get_order(order_id) or {}
            venta_id = order.get("venta_id")
            if venta_id:
                self.db.execute("UPDATE ventas SET total=? WHERE id=?", (new_total, venta_id))
        except Exception as exc:
            logger.debug("_sync_venta_total: %s", exc)

    def _notify_adjustment_pending(self, order: Dict[str, Any], item_name: str, requested_qty: float,
                                   prepared_qty: float, unit: str, new_subtotal: float,
                                   diff_qty: float) -> bool:
        phone = order.get("cliente_tel") or ""
        if not phone:
            return False
        folio = order.get("folio") or f"DEL-{order.get('id','')}"
        sign = "+" if diff_qty >= 0 else ""
        msg = (
            f"⚖️ *Ajuste de tu pedido {folio}*\n\n"
            f"Producto: {item_name}\n"
            f"Solicitado: {requested_qty:.3g} {unit}\n"
            f"Preparado: {prepared_qty:.3g} {unit} ({sign}{diff_qty:.3g} {unit})\n"
            f"Nuevo subtotal: ${new_subtotal:,.2f}\n\n"
            "La diferencia supera la tolerancia permitida de ±0.2 unidades.\n"
            "Responde *ACEPTAR AJUSTE* para autorizarlo o *RECHAZAR AJUSTE* para mantener el pedido sin ese cambio."
        )
        try:
            from core.integrations.whatsapp_client import WhatsAppClient
            return bool(WhatsAppClient().enviar_mensaje(phone, msg))
        except Exception as exc:
            logger.warning("No se pudo notificar ajuste pendiente por WhatsApp: %s", exc)
            return False

    def adjust_item_weight(
        self,
        order_id: int,
        item_id: int,
        prepared_qty: float,
        prepared_by: str,
        adjustment_reason: str = "",
        unit: str = "kg",
    ) -> Dict[str, Any]:
        """Registra ajuste de peso/cantidad.

        Reglas:
        - Solo se permite en estado `preparacion`.
        - Tolerancia en unidades: ±0.2 por defecto.
        - Si excede tolerancia, NO aplica el ajuste: queda pendiente de aceptación.
        - Si está dentro de tolerancia, aplica cantidad/subtotal/total inmediatamente.
        """
        from core.services.reservation_service import ReservationService, TOLERANCE_UNITS

        order = self.repository.get_order(order_id) or {}
        estado = (order.get("estado") or "").lower()
        if estado != "preparacion":
            raise ValueError("El ajuste de peso/cantidad solo puede hacerse en estado 'preparacion'.")

        item_row = self.db.execute(
            "SELECT precio_unitario, cantidad, nombre FROM delivery_items WHERE id=? AND delivery_id=?",
            (item_id, order_id),
        ).fetchone()
        if not item_row:
            raise ValueError(f"delivery_items.id={item_id} not found for order={order_id}")

        unit_price = float(item_row[0] or 0)
        requested_qty = float(item_row[1] or prepared_qty)
        item_name = item_row[2] or "Producto"
        adj = ReservationService.compute_adjustment(
            requested_qty, prepared_qty, unit_price, tolerance_units=TOLERANCE_UNITS
        )

        if adj["tolerance_exceeded"]:
            token = uuid.uuid4().hex
            self.db.execute(
                """UPDATE delivery_items
                   SET pending_prepared_qty=?, pending_subtotal=?,
                       adjustment_status=?, adjustment_requested_at=datetime('now'),
                       adjustment_response='', adjustment_token=?, tolerance_units=?,
                       prepared_by=?, adjustment_reason=?, tolerance_exceeded=1
                   WHERE id=? AND delivery_id=?""",
                (
                    prepared_qty, adj["new_subtotal"], ADJUSTMENT_PENDING,
                    token, adj["tolerance_units"], prepared_by, adjustment_reason,
                    item_id, order_id,
                ),
            )
            self.db.execute(
                "UPDATE delivery_orders SET adjustment_pending=1, adjustment_blocked_state='en_ruta' WHERE id=?",
                (order_id,),
            )
            try:
                self.db.commit()
            except Exception:
                pass
            self._notify_adjustment_pending(
                order, item_name, requested_qty, prepared_qty, unit,
                adj["new_subtotal"], adj["diff_qty"]
            )
            self._publish("DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED", {
                "order_id": order_id,
                "item_id": item_id,
                "folio": order.get("folio") or str(order_id),
                "cliente_tel": order.get("cliente_tel", ""),
                "requested_qty": requested_qty,
                "prepared_qty": prepared_qty,
                "diff_qty": adj["diff_qty"],
                "tolerance_units": adj["tolerance_units"],
                "db": self.db,
            })
            return {**adj, "status": ADJUSTMENT_PENDING, "applied": False}

        # Dentro de tolerancia: aplicar inmediatamente.
        self.db.execute(
            """UPDATE delivery_items
               SET cantidad=?, prepared_qty=?, final_qty=?, subtotal=?,
                   prepared_by=?, prepared_at=datetime('now'),
                   adjustment_reason=?, tolerance_exceeded=0,
                   adjustment_status=?, pending_prepared_qty=NULL, pending_subtotal=NULL,
                   adjustment_responded_at=datetime('now'), adjustment_response='auto_accepted'
               WHERE id=? AND delivery_id=?""",
            (
                prepared_qty, prepared_qty, prepared_qty, adj["new_subtotal"],
                prepared_by, adjustment_reason, ADJUSTMENT_ACCEPTED,
                item_id, order_id,
            ),
        )
        new_total = self._recalculate_order_total(order_id)
        self._sync_venta_total(order_id, new_total)
        try:
            self.db.commit()
        except Exception:
            pass

        self._publish("DELIVERY_ITEM_WEIGHT_ADJUSTED", {
            "order_id": order_id,
            "item_id": item_id,
            "item_name": item_name,
            "requested_qty": requested_qty,
            "prepared_qty": prepared_qty,
            "unit_price": unit_price,
            "unit": unit,
            "prepared_by": prepared_by,
            "adjustment_reason": adjustment_reason,
            "new_total": new_total,
            "folio": order.get("folio") or str(order_id),
            "cliente_tel": order.get("cliente_tel", ""),
            "cliente_email": order.get("cliente_email", ""),
            "db": self.db,
        })
        logger.info(
            "adjust_item_weight: order=%s item=%s requested=%.3f prepared=%.3f diff=%.3f tolerance_units=%.3f exceeded=%s",
            order_id, item_id, requested_qty, prepared_qty,
            adj["diff_qty"], adj["tolerance_units"], adj["tolerance_exceeded"],
        )
        return {**adj, "status": ADJUSTMENT_ACCEPTED, "applied": True, "new_total": new_total}

    def get_order_items(self, order_id: int) -> List[Dict[str, Any]]:
        try:
            rows = self.db.execute(
                """SELECT id, nombre, cantidad, precio_unitario, subtotal, unidad,
                          producto_id, requested_qty, prepared_qty, final_qty,
                          prepared_by, prepared_at, adjustment_reason, tolerance_exceeded,
                          pending_prepared_qty, pending_subtotal, adjustment_status,
                          adjustment_requested_at, adjustment_responded_at, adjustment_response,
                          tolerance_units
                   FROM delivery_items WHERE delivery_id=? ORDER BY id""",
                (order_id,),
            ).fetchall()
            cols = ["id", "nombre", "cantidad", "precio_unitario", "subtotal", "unidad",
                    "producto_id", "requested_qty", "prepared_qty", "final_qty",
                    "prepared_by", "prepared_at", "adjustment_reason", "tolerance_exceeded",
                    "pending_prepared_qty", "pending_subtotal", "adjustment_status",
                    "adjustment_requested_at", "adjustment_responded_at", "adjustment_response",
                    "tolerance_units"]
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
