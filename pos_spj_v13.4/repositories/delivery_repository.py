from __future__ import annotations

import json
from backend.shared.ids import new_uuid
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.repositories.delivery")


class DeliveryRepository:
    """Capa de acceso a datos para delivery_orders y su trazabilidad."""

    def __init__(self, db):
        self.db = db
        self.ensure_schema()

    def ensure_schema(self) -> None:
        """Deprecated compatibility shim; schema ownership lives in DeliverySchemaMigrator."""
        from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator

        DeliverySchemaMigrator(self.db).ensure_schema()

    @staticmethod
    def _normalize_status(status: str) -> str:
        mapping = {
            "asignado": "preparacion",
            "listo": "preparacion",
            "en_camino": "en_ruta",
        }
        return mapping.get((status or "").strip().lower(), (status or "pendiente").strip().lower())

    def list_orders(self, estado: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        sql = (
            "SELECT d.*, v.id as venta_relacionada, dr.nombre AS driver_nombre "
            "FROM delivery_orders d "
            "LEFT JOIN ventas v ON v.id = d.venta_id "
            "LEFT JOIN drivers dr ON dr.id = d.driver_id "
            "WHERE 1=1 "
        )
        params: List[Any] = []
        if estado and estado != "Todos":
            sql += " AND lower(d.estado) = ?"
            params.append(self._normalize_status(estado))
        sql += " ORDER BY COALESCE(d.fecha_actualizacion,d.fecha) DESC LIMIT ?"
        params.append(limit)

        rows = self.db.execute(sql, tuple(params)).fetchall()
        result: List[Dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            item["estado"] = self._normalize_status(item.get("estado"))
            item["venta_validada"] = bool(item.get("venta_relacionada") or not item.get("venta_id"))
            result.append(item)
        return result

    def create_order(self, data: Dict[str, Any], *, commit: bool = True) -> str:
        usuario = data.get("usuario", "sistema")
        hist = [self._legacy_history_entry("pendiente", usuario, reason="creación")]
        oid = data.get("id") or new_uuid()  # REGLA CERO: UUIDv7, sin lastrowid
        self.db.execute(
            """
            INSERT INTO delivery_orders(
                id, venta_id, folio, whatsapp_order_id, cliente_id, cliente_nombre, cliente_tel,
                direccion, lat, lng, estado, notas, total, usuario, historial_cambios,
                sucursal_id, workflow_type, delivery_type, scheduled_at, source_channel
            ) VALUES(?,?,?,?,?,?,?,?,?,?,'pendiente',?,?,?,?,?,?,?,?,?)
            """,
            (
                oid,
                data.get("venta_id"),
                data.get("folio"),
                data.get("whatsapp_order_id"),
                data.get("cliente_id"),
                data.get("cliente_nombre"),
                data.get("cliente_tel"),
                data.get("direccion") or "Sin dirección",
                data.get("lat"),
                data.get("lng"),
                data.get("notas", ""),
                float(data.get("total", 0) or 0),
                usuario,
                json.dumps(hist, ensure_ascii=False),
                data.get("sucursal_id") or None,
                data.get("workflow_type"),
                data.get("delivery_type"),
                data.get("scheduled_at"),
                data.get("source_channel", "whatsapp"),
            ),
        )
        self._replace_items(oid, data.get("items") or [])
        self._insert_history(
            oid,
            None,
            "pendiente",
            usuario,
            "creación",
            reason="order_created",
            metadata={"source_channel": data.get("source_channel", "whatsapp"), "venta_id": data.get("venta_id")},
        )
        if commit:
            self.db.commit()
        return oid

    def upsert_order_from_whatsapp(self, payload: Dict[str, Any], usuario: str = "whatsapp") -> int:
        wa_id = payload.get("whatsapp_order_id") or payload.get("order_id")
        venta_id = payload.get("venta_id") or payload.get("id")
        row = None
        if wa_id:
            row = self.db.execute(
                "SELECT id FROM delivery_orders WHERE whatsapp_order_id=?", (str(wa_id),)
            ).fetchone()
        if not row and venta_id:
            row = self.db.execute(
                "SELECT id FROM delivery_orders WHERE venta_id=?", (str(venta_id),)
            ).fetchone()

        data = {
            "venta_id": str(venta_id) if venta_id else None,
            "folio": payload.get("folio") or payload.get("codigo"),
            "whatsapp_order_id": str(wa_id or f"venta:{venta_id}"),
            "cliente_id": payload.get("cliente_id"),
            "cliente_nombre": payload.get("cliente") or payload.get("cliente_nombre"),
            "cliente_tel": payload.get("telefono") or payload.get("cliente_tel") or payload.get("cliente_telefono"),
            "workflow_type": payload.get("workflow_type"),
            "delivery_type": payload.get("delivery_type") or payload.get("tipo_entrega"),
            "scheduled_at": payload.get("scheduled_at") or payload.get("fecha_entrega_programada"),
            "source_channel": payload.get("source_channel") or "whatsapp",
            "direccion": payload.get("direccion") or payload.get("direccion_entrega") or "Sin dirección",
            "lat": payload.get("lat"),
            "lng": payload.get("lng"),
            "total": payload.get("total") or 0,
            "notas": payload.get("notas", ""),
            "usuario": usuario,
            "sucursal_id": payload.get("sucursal_id", 1),
            "items": payload.get("items") or [],
        }
        if row:
            oid = str(row[0])
            self.db.execute(
                """
                UPDATE delivery_orders
                SET venta_id=COALESCE(?, venta_id),
                    folio=COALESCE(?, folio),
                    whatsapp_order_id=COALESCE(?, whatsapp_order_id),
                    cliente_id=COALESCE(?, cliente_id),
                    cliente_nombre=COALESCE(NULLIF(?,''), cliente_nombre),
                    cliente_tel=COALESCE(NULLIF(?,''), cliente_tel),
                    direccion=COALESCE(NULLIF(?,''), direccion),
                    lat=COALESCE(?,lat), lng=COALESCE(?,lng), total=COALESCE(?,total),
                    notas=COALESCE(NULLIF(?,''),notas), fecha_actualizacion=datetime('now')
                WHERE id=?
                """,
                (
                    data["venta_id"], data["folio"], data["whatsapp_order_id"], data["cliente_id"],
                    data["cliente_nombre"], data["cliente_tel"], data["direccion"],
                    data["lat"], data["lng"], data["total"], data["notas"], oid,
                ),
            )
            if data["items"]:
                self._replace_items(oid, data["items"])
        else:
            oid = self.create_order(data)
        self.db.commit()
        return oid

    def _replace_items(self, order_id: int, items: List[Dict[str, Any]]) -> None:
        """Sincroniza delivery_items desde el payload WA sin duplicar líneas."""
        try:
            self.db.execute("DELETE FROM delivery_items WHERE delivery_id=?", (order_id,))
            for it in items:
                qty = float(it.get("cantidad") or it.get("qty") or 0)
                price = float(it.get("precio_unitario") or it.get("precio") or it.get("unit_price") or 0)
                subtotal = float(it.get("subtotal") or (qty * price))
                self.db.execute(
                    """
                    INSERT INTO delivery_items(
                        id, delivery_id, producto_id, nombre, cantidad,
                        precio_unitario, subtotal, unidad, requested_qty
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        new_uuid(),
                        order_id,
                        it.get("producto_id"),
                        it.get("nombre") or it.get("name") or "Producto",
                        qty,
                        price,
                        subtotal,
                        it.get("unidad") or "",
                        qty,
                    ),
                )
        except Exception as exc:
            logger.warning("_replace_items delivery_id=%s falló: %s", order_id, exc)

    def update_status(
        self,
        order_id: int,
        new_status: str,
        usuario: str,
        observacion: str = "",
        responsable: str = "",
        *,
        commit: bool = True,
        reason: str | None = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: int | None = None,
    ) -> None:
        row = self.db.execute(
            "SELECT estado, historial_cambios, venta_id FROM delivery_orders WHERE id=?", (order_id,)
        ).fetchone()
        if not row:
            raise ValueError("Pedido no encontrado")
        prev = self._normalize_status(row[0])
        new_status = self._normalize_status(new_status)
        hist = self._append_legacy_history(row[1], new_status, usuario, reason=reason or observacion or "status_changed")
        self.db.execute(
            """
            UPDATE delivery_orders
            SET estado=?, responsable_entrega=COALESCE(?, responsable_entrega),
                usuario=?, fecha_actualizacion=datetime('now'), historial_cambios=?
            WHERE id=?
            """,
            (new_status, responsable or None, usuario, json.dumps(hist, ensure_ascii=False), order_id),
        )
        # ventas is a secondary projection; SaleDeliveryProjectionService owns sale updates.
        history_metadata = {"responsable": responsable or "", "venta_id": row[2]}
        if metadata:
            history_metadata.update(metadata)
        self._insert_history(
            order_id,
            prev,
            new_status,
            usuario,
            observacion,
            reason=reason or "status_changed",
            metadata=history_metadata,
            event_id=event_id,
        )
        if commit:
            self.db.commit()

    def _legacy_history_entry(self, status: str, usuario: str, *, reason: str = "") -> Dict[str, Any]:
        return {
            "estado": self._normalize_status(status),
            "usuario": usuario,
            "reason": reason,
            "created_at": self.db.execute("SELECT datetime('now')").fetchone()[0],
        }

    def _append_legacy_history(self, raw_history: str | None, status: str, usuario: str, *, reason: str = "") -> List[Dict[str, Any]]:
        hist: List[Dict[str, Any]] = []
        if raw_history:
            try:
                parsed = json.loads(raw_history)
                hist = parsed if isinstance(parsed, list) else []
            except Exception as exc:
                logger.warning("historial_cambios inválido para delivery: %s", exc)
        hist.append(self._legacy_history_entry(status, usuario, reason=reason))
        return hist

    def _insert_history(
        self,
        order_id: int,
        old: Optional[str],
        new: str,
        usuario: str,
        obs: str,
        *,
        reason: str | None = None,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: int | None = None,
    ) -> None:
        columns = self._columns("delivery_order_history")
        values: Dict[str, Any] = {
            "id": new_uuid(),
            "order_id": order_id,
            "estado_anterior": old,
            "estado_nuevo": new,
            "usuario": usuario,
            "observacion": obs,
        }
        if "fecha" in columns:
            values["fecha"] = self.db.execute("SELECT datetime('now')").fetchone()[0]
        if "reason" in columns:
            values["reason"] = reason or obs or "status_changed"
        if "metadata_json" in columns:
            values["metadata_json"] = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
        if "event_id" in columns:
            values["event_id"] = event_id
        if "created_at" in columns:
            values["created_at"] = self.db.execute("SELECT datetime('now')").fetchone()[0]

        insert_columns = [col for col in values if col in columns]
        placeholders = ",".join("?" for _ in insert_columns)
        self.db.execute(
            f"INSERT INTO delivery_order_history({', '.join(insert_columns)}) VALUES({placeholders})",
            tuple(values[col] for col in insert_columns),
        )

    def iter_pending_whatsapp_sales(self, limit: int = 200) -> List[Dict[str, Any]]:
        if not self._table_exists("ventas") or not self._table_exists("delivery_orders"):
            return []
        cols_ventas = self._columns("ventas")
        cols_det = self._columns("detalles_venta") if self._table_exists("detalles_venta") else set()
        if "id" not in cols_ventas:
            return []

        where = ["1=1"]
        if "canal" in cols_ventas:
            where.append("lower(canal)='whatsapp'")
        if "estado" in cols_ventas:
            where.append("lower(estado) IN ('pendiente','pendiente_wa','en_preparacion','preparacion','en_ruta','programado')")
        rows = self.db.execute(
            f"SELECT * FROM ventas WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        sales: List[Dict[str, Any]] = []
        for row in rows:
            sale = dict(row)
            venta_id = sale.get("id")
            items: List[Dict[str, Any]] = []
            if venta_id and cols_det and "venta_id" in cols_det:
                nombre_expr = "COALESCE(producto_nombre,'') AS producto_nombre" if "producto_nombre" in cols_det else "'' AS producto_nombre"
                precio_expr = "COALESCE(precio_unitario,0) AS precio_unitario" if "precio_unitario" in cols_det else "0 AS precio_unitario"
                subtotal_expr = "COALESCE(subtotal,0) AS subtotal" if "subtotal" in cols_det else "0 AS subtotal"
                det_rows = self.db.execute(
                    f"SELECT producto_id, {nombre_expr}, "
                    f"COALESCE(cantidad,0) AS cantidad, {precio_expr}, "
                    f"{subtotal_expr} "
                    "FROM detalles_venta WHERE venta_id=?",
                    (venta_id,),
                ).fetchall()
                items = [dict(r) for r in det_rows]
            sale["items"] = items
            sales.append(sale)
        return sales

    def _table_exists(self, table: str) -> bool:
        return bool(self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
        ).fetchone())

    def _columns(self, table: str) -> set[str]:
        return {r[1] for r in self.db.execute(f"PRAGMA table_info({table})").fetchall()}

    def has_pending_adjustment(self, order_id: int) -> bool:
        row = self.db.execute(
            """SELECT 1 FROM delivery_items
               WHERE delivery_id=? AND adjustment_status=? LIMIT 1""",
            (order_id, "pending_customer"),
        ).fetchone()
        return row is not None

    def mark_adjustment_blocked(self, order_id: int, target_status: str, *, commit: bool = True) -> None:
        self.db.execute(
            "UPDATE delivery_orders SET adjustment_pending=1, adjustment_blocked_state=? WHERE id=?",
            (target_status, order_id),
        )
        if commit:
            self.db.commit()

    def activate_scheduled_order(
        self,
        order_id: int,
        workflow_type: str,
        *,
        usuario: str = "sistema",
        commit: bool = True,
    ) -> None:
        row = self.db.execute(
            "SELECT estado, historial_cambios, venta_id FROM delivery_orders WHERE id=?",
            (order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Pedido no encontrado")
        prev = self._normalize_status(row[0])
        hist = self._append_legacy_history(row[1], "pendiente", usuario, reason="scheduled_order_activated")
        self.db.execute(
            """
            UPDATE delivery_orders
            SET workflow_type=?, estado='pendiente', fecha_actualizacion=datetime('now'),
                usuario=?, historial_cambios=?
            WHERE id=?
            """,
            (workflow_type, usuario, json.dumps(hist, ensure_ascii=False), order_id),
        )
        self._insert_history(
            order_id,
            prev,
            "pendiente",
            usuario,
            "activación de pedido programado",
            reason="scheduled_order_activated",
            metadata={"workflow_type": workflow_type, "venta_id": row[2]},
        )
        if commit:
            self.db.commit()

    def get_item_for_weight_adjustment(self, order_id: int, item_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute(
            "SELECT id, precio_unitario, cantidad, nombre FROM delivery_items WHERE id=? AND delivery_id=?",
            (item_id, order_id),
        ).fetchone()
        return dict(row) if row else None

    def mark_item_adjustment_pending(
        self,
        *,
        order_id: int,
        item_id: int,
        prepared_qty: float,
        pending_subtotal: float,
        token: str,
        tolerance_units: float,
        prepared_by: str,
        adjustment_reason: str,
        commit: bool = True,
    ) -> None:
        self.db.execute(
            """UPDATE delivery_items
               SET pending_prepared_qty=?, pending_subtotal=?,
                   adjustment_status=?, adjustment_requested_at=datetime('now'),
                   adjustment_response='', adjustment_token=?, tolerance_units=?,
                   prepared_by=?, adjustment_reason=?, tolerance_exceeded=1
               WHERE id=? AND delivery_id=?""",
            (
                prepared_qty,
                pending_subtotal,
                "pending_customer",
                token,
                tolerance_units,
                prepared_by,
                adjustment_reason,
                item_id,
                order_id,
            ),
        )
        self.db.execute(
            "UPDATE delivery_orders SET adjustment_pending=1, adjustment_blocked_state='en_ruta' WHERE id=?",
            (order_id,),
        )
        if commit:
            self.db.commit()

    def apply_item_weight_adjustment(
        self,
        *,
        order_id: int,
        item_id: int,
        prepared_qty: float,
        subtotal: float,
        prepared_by: str,
        adjustment_reason: str,
    ) -> None:
        self.db.execute(
            """UPDATE delivery_items
               SET cantidad=?, prepared_qty=?, final_qty=?, subtotal=?,
                   prepared_by=?, prepared_at=datetime('now'),
                   adjustment_reason=?, tolerance_exceeded=0,
                   adjustment_status=?, pending_prepared_qty=NULL, pending_subtotal=NULL,
                   adjustment_responded_at=datetime('now'), adjustment_response='auto_accepted'
               WHERE id=? AND delivery_id=?""",
            (
                prepared_qty,
                prepared_qty,
                prepared_qty,
                subtotal,
                prepared_by,
                adjustment_reason,
                "accepted",
                item_id,
                order_id,
            ),
        )


    def get_order_total(self, order_id: int) -> float:
        row = self.db.execute("SELECT COALESCE(total, 0) FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        return round(float(row[0]) if row else 0.0, 2)

    def list_item_subtotals_for_order(self, order_id: int) -> List[float]:
        rows = self.db.execute(
            "SELECT COALESCE(subtotal, 0) AS subtotal FROM delivery_items WHERE delivery_id=?",
            (order_id,),
        ).fetchall()
        return [float(row[0]) for row in rows]

    def update_order_total(
        self,
        order_id: int,
        total: float,
        *,
        mark_weight_adjusted: bool = True,
        commit: bool = True,
    ) -> None:
        cols = self._columns("delivery_orders")
        if mark_weight_adjusted and "weight_adjusted" in cols:
            self.db.execute(
                "UPDATE delivery_orders SET total=?, weight_adjusted=1 WHERE id=?",
                (float(total), order_id),
            )
        else:
            self.db.execute("UPDATE delivery_orders SET total=? WHERE id=?", (float(total), order_id))
        if commit:
            self.db.commit()

    def list_active_branches(self) -> List[Dict[str, Any]]:
        """Return active branches as list of dicts with id and nombre."""
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM sucursales WHERE activo=1 ORDER BY id"
            ).fetchall()
            return [{"id": r[0], "nombre": r[1]} for r in rows]
        except Exception:
            return []

    def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute("SELECT * FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None
