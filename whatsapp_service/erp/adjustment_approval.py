# erp/adjustment_approval.py — Aceptar/rechazar ajustes Delivery desde WhatsApp
"""
Permite que el cliente autorice o rechace ajustes de peso/cantidad cuando la
variación supera la tolerancia de ±0.2 unidades.

El microservicio corre separado del ERP desktop, por eso este handler aplica la
respuesta directamente sobre la BD del ERP.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Dict
from core.delivery.domain.events import DeliveryEvents
from core.services.order_total_service import OrderTotalService
from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService
from phone_number import possible_match_key

logger = logging.getLogger("wa.adjustment_approval")


def _clean_phone(phone: str) -> str:
    return possible_match_key(phone)


def _row_to_dict(row) -> Dict:
    return dict(row) if row else {}


class AdjustmentApprovalService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.db.row_factory = sqlite3.Row

    def has_pending_for_phone(self, phone: str) -> bool:
        phone10 = _clean_phone(phone)
        if not phone10:
            return False
        row = self.db.execute(
            """
            SELECT 1
            FROM delivery_items di
            JOIN delivery_orders d ON d.id = di.delivery_id
            WHERE di.adjustment_status='pending_customer'
              AND REPLACE(REPLACE(REPLACE(COALESCE(d.cliente_tel,''), '+',''), ' ', ''), '-', '') LIKE ?
            LIMIT 1
            """,
            (f"%{phone10}",),
        ).fetchone()
        return row is not None

    def respond_latest_for_phone(self, phone: str, accepted: bool) -> Dict:
        phone10 = _clean_phone(phone)
        if not phone10:
            return {"ok": False, "error": "telefono invalido"}

        row = self.db.execute(
            """
            SELECT di.*, d.id AS order_id, d.folio, d.venta_id, d.total AS order_total,
                   d.cliente_tel, d.cliente_nombre
            FROM delivery_items di
            JOIN delivery_orders d ON d.id = di.delivery_id
            WHERE di.adjustment_status='pending_customer'
              AND REPLACE(REPLACE(REPLACE(COALESCE(d.cliente_tel,''), '+',''), ' ', ''), '-', '') LIKE ?
            ORDER BY datetime(COALESCE(di.adjustment_requested_at, '1970-01-01')) DESC, di.id DESC
            LIMIT 1
            """,
            (f"%{phone10}",),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "no hay ajustes pendientes"}

        data = _row_to_dict(row)
        order_id = int(data["order_id"])
        item_id = int(data["id"])
        venta_id = data.get("venta_id")
        folio = data.get("folio") or f"DEL-{order_id}"

        if accepted:
            pending_qty = float(data.get("pending_prepared_qty") or data.get("cantidad") or 0)
            pending_subtotal = float(data.get("pending_subtotal") or (pending_qty * float(data.get("precio_unitario") or 0)))
            self.db.execute(
                """
                UPDATE delivery_items
                SET cantidad=?, prepared_qty=?, final_qty=?, subtotal=?,
                    adjustment_status='accepted', adjustment_response='accepted_by_customer',
                    adjustment_responded_at=datetime('now'), pending_prepared_qty=NULL,
                    pending_subtotal=NULL
                WHERE id=?
                """,
                (pending_qty, pending_qty, pending_qty, pending_subtotal, item_id),
            )
            action = "accepted"
        else:
            self.db.execute(
                """
                UPDATE delivery_items
                SET adjustment_status='rejected', adjustment_response='rejected_by_customer',
                    adjustment_responded_at=datetime('now'), pending_prepared_qty=NULL,
                    pending_subtotal=NULL, tolerance_exceeded=0
                WHERE id=?
                """,
                (item_id,),
            )
            action = "rejected"

        # Recalcular total del pedido desde delivery_items; ventas se actualiza solo vía proyección controlada.
        old_total = round(float(data.get("order_total") or 0), 2)
        new_total = OrderTotalService(self.db).recalculate_order_total(order_id)
        SaleDeliveryProjectionService(self.db).project_total(venta_id, new_total)
        pending_left = self.db.execute(
            "SELECT 1 FROM delivery_items WHERE delivery_id=? AND adjustment_status='pending_customer' LIMIT 1",
            (order_id,),
        ).fetchone()
        pending_flag = 1 if pending_left else 0

        self.db.execute(
            "UPDATE delivery_orders SET adjustment_pending=?, adjustment_blocked_state='' WHERE id=?",
            (pending_flag, order_id),
        )

        event_type = "DELIVERY_ADJUSTMENT_ACCEPTED" if accepted else "DELIVERY_ADJUSTMENT_REJECTED"
        try:
            self.db.execute(
                """
                INSERT INTO wa_event_log(event_type, data_json, sucursal_id, prioridad, timestamp)
                SELECT ?,
                       json_object('order_id', ?, 'old_total', ?, 'new_total', ?, 'folio', ?, 'cliente_tel', COALESCE(cliente_tel,'')),
                       COALESCE(sucursal_id,1), 35, datetime('now')
                FROM delivery_orders WHERE id=?
                """,
                (DeliveryEvents.TOTAL_UPDATED.value, order_id, old_total, new_total, folio, order_id),
            )
            self.db.execute(
                """
                INSERT INTO wa_event_log(event_type, data_json, sucursal_id, prioridad, timestamp)
                SELECT ?,
                       json_object('order_id', ?, 'item_id', ?, 'folio', ?, 'response', ?, 'total', ?),
                       COALESCE(sucursal_id,1), 40, datetime('now')
                FROM delivery_orders WHERE id=?
                """,
                (event_type, order_id, item_id, folio, action, new_total, order_id),
            )
        except Exception as exc:
            logger.warning("No se pudo registrar evento de ajuste delivery order=%s item=%s: %s", order_id, item_id, exc)

        self.db.commit()
        return {
            "ok": True,
            "order_id": order_id,
            "item_id": item_id,
            "folio": folio,
            "accepted": bool(accepted),
            "total": new_total,
            "pending_left": bool(pending_flag),
        }
