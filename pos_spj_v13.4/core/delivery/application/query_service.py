"""DeliveryQueryService — read-only queries for the Delivery UI.

All DB reads for the UI layer must go through this service. No SQL in UI.
Maps legacy DB string values to canonical domain enums.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from core.delivery.application.action_policy import DeliveryActionPolicy
from core.delivery.application.dto import DeliveryItemViewDTO, DeliveryOrderViewDTO
from core.delivery.domain.value_objects import (
    DeliveryStatus,
    FulfillmentType,
    LEGACY_STATUS_MAP,
    LEGACY_UNIT_MAP,
    PaymentStatus,
    STATUS_LABELS_ES,
    UNIT_LABELS_ES,
    UnitCode,
    WEIGHABLE_UNITS,
)

logger = logging.getLogger("spj.delivery.application.query_service")

_ACTION_POLICY = DeliveryActionPolicy()


def _map_legacy_status(raw: str | None) -> DeliveryStatus:
    """Map a legacy DB status string to DeliveryStatus enum."""
    normalized = (raw or "").strip().lower()
    if normalized in LEGACY_STATUS_MAP:
        return LEGACY_STATUS_MAP[normalized]
    logger.debug("Unknown delivery status %r — defaulting to PENDING", raw)
    return DeliveryStatus.PENDING


def _map_legacy_fulfillment(raw: str | None) -> FulfillmentType:
    """Map a legacy delivery_type string to FulfillmentType enum."""
    normalized = (raw or "").strip().lower()
    if normalized in ("pickup", "sucursal", "counter"):
        return FulfillmentType.PICKUP
    # domicilio, delivery, whatsapp, etc.
    return FulfillmentType.DELIVERY


def _map_legacy_unit(raw: str | None) -> UnitCode:
    """Map a legacy unidad string from productos table to UnitCode enum."""
    normalized = (raw or "").strip().lower()
    if normalized in LEGACY_UNIT_MAP:
        return LEGACY_UNIT_MAP[normalized]
    if normalized:
        logger.warning("Unknown unit %r — defaulting to PIECE", raw)
    return UnitCode.PIECE


def _map_payment_status(row: dict[str, Any]) -> PaymentStatus:
    """Infer payment status from order fields."""
    pago_metodo = str(row.get("pago_metodo") or "").lower()
    pago_monto = float(row.get("pago_monto") or 0)
    total = float(row.get("total") or 0)
    if pago_metodo in ("ya pagado (online)", "ya_pagado", "online"):
        return PaymentStatus.PAID
    if pago_monto > 0 and total > 0:
        if pago_monto >= total * 0.99:  # within 1% tolerance
            return PaymentStatus.PAID
        return PaymentStatus.PARTIAL
    return PaymentStatus.PENDING


class DeliveryQueryService:
    """Read-only query service for delivery orders.

    Accepts a db connection (SQLite connection or compatible object).
    Returns typed DTOs — no raw dicts exposed to UI.
    """

    def __init__(self, db: Any) -> None:
        self._db = db

    def list_orders(
        self,
        branch_id: str | None = None,
        status: DeliveryStatus | None = None,
        fulfillment_type: FulfillmentType | None = None,
        date: str | None = None,
    ) -> list[DeliveryOrderViewDTO]:
        """Return delivery orders as typed DTOs.

        Args:
            branch_id: Filter by branch UUID/ID (None = all branches).
            status: Filter by DeliveryStatus enum (None = all statuses).
            fulfillment_type: Filter by FulfillmentType (None = all).
            date: Filter by date string ISO format YYYY-MM-DD (None = all dates).

        Returns:
            List of DeliveryOrderViewDTO sorted by created_at DESC.
        """
        try:
            orders_raw = self._fetch_orders(branch_id=branch_id, date=date)
        except Exception as exc:
            logger.exception("DeliveryQueryService.list_orders DB error: %s", exc)
            return []

        result: list[DeliveryOrderViewDTO] = []
        for raw in orders_raw:
            dto = self._build_order_dto(raw)
            if dto is None:
                continue

            # Apply enum-level filters (after mapping)
            if status is not None and dto.status != status:
                continue
            if fulfillment_type is not None and dto.fulfillment_type != fulfillment_type:
                continue

            result.append(dto)

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fetch_orders(
        self, branch_id: str | None, date: str | None
    ) -> list[dict[str, Any]]:
        """Execute the DB query and return raw row dicts."""
        where_clauses: list[str] = []
        params: list[Any] = []

        if branch_id is not None:
            where_clauses.append("o.sucursal_id = ?")
            params.append(branch_id)

        if date is not None:
            where_clauses.append("DATE(o.fecha_solicitud) = ?")
            params.append(date)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT
                o.id,
                COALESCE(o.folio, '') AS folio,
                COALESCE(o.sucursal_id, '') AS branch_id,
                COALESCE(o.cliente_nombre, '') AS customer_name,
                COALESCE(o.cliente_tel, '') AS customer_tel,
                COALESCE(o.delivery_type, '') AS delivery_type,
                COALESCE(o.estado, 'pendiente') AS estado,
                COALESCE(o.pago_metodo, '') AS pago_metodo,
                COALESCE(o.pago_monto, 0) AS pago_monto,
                o.driver_id,
                COALESCE(d.nombre, '') AS driver_name,
                COALESCE(o.fecha_solicitud, '') AS created_at,
                COALESCE(o.total, 0) AS total,
                o.adjustment_pending,
                COALESCE(o.workflow_type, '') AS workflow_type
            FROM delivery_orders o
            LEFT JOIN drivers d ON d.id = o.driver_id
            {where_sql}
            ORDER BY o.fecha_solicitud DESC
            LIMIT 500
        """
        try:
            rows = self._db.execute(sql, params).fetchall()
        except Exception:
            # Fallback without driver join if drivers table doesn't exist
            sql_fallback = f"""
                SELECT
                    id,
                    COALESCE(folio, '') AS folio,
                    COALESCE(sucursal_id, '') AS branch_id,
                    COALESCE(cliente_nombre, '') AS customer_name,
                    COALESCE(cliente_tel, '') AS customer_tel,
                    COALESCE(delivery_type, '') AS delivery_type,
                    COALESCE(estado, 'pendiente') AS estado,
                    COALESCE(pago_metodo, '') AS pago_metodo,
                    COALESCE(pago_monto, 0) AS pago_monto,
                    driver_id,
                    '' AS driver_name,
                    COALESCE(fecha_solicitud, '') AS created_at,
                    COALESCE(total, 0) AS total,
                    adjustment_pending,
                    COALESCE(workflow_type, '') AS workflow_type
                FROM delivery_orders
                {where_sql}
                ORDER BY fecha_solicitud DESC
                LIMIT 500
            """
            rows = self._db.execute(sql_fallback, params).fetchall()

        # Convert rows to dicts
        if rows and hasattr(rows[0], "keys"):
            return [dict(r) for r in rows]
        # Positional fallback
        keys = [
            "id", "folio", "branch_id", "customer_name", "customer_tel",
            "delivery_type", "estado", "pago_metodo", "pago_monto",
            "driver_id", "driver_name", "created_at", "total",
            "adjustment_pending", "workflow_type",
        ]
        return [dict(zip(keys, r)) for r in rows]

    def _fetch_items(self, order_id: Any) -> list[dict[str, Any]]:
        """Fetch line items for one order."""
        try:
            sql = """
                SELECT
                    COALESCE(i.id, '') AS item_id,
                    COALESCE(i.producto_id, '') AS product_id,
                    COALESCE(p.nombre, i.nombre, '') AS product_name,
                    COALESCE(i.cantidad, 0) AS requested_quantity,
                    i.prepared_qty AS actual_quantity,
                    COALESCE(p.unidad, i.unidad, '') AS unidad,
                    COALESCE(p.stock, 0) AS available_stock
                FROM delivery_items i
                LEFT JOIN productos p ON p.id = i.producto_id
                WHERE i.delivery_id = ?
                ORDER BY i.id
                LIMIT 100
            """
            rows = self._db.execute(sql, (order_id,)).fetchall()
        except Exception:
            try:
                sql_fallback = """
                    SELECT
                        COALESCE(id, '') AS item_id,
                        COALESCE(producto_id, '') AS product_id,
                        COALESCE(nombre, '') AS product_name,
                        COALESCE(cantidad, 0) AS requested_quantity,
                        NULL AS actual_quantity,
                        COALESCE(unidad, '') AS unidad,
                        0 AS available_stock
                    FROM delivery_items
                    WHERE delivery_id = ?
                    ORDER BY id
                    LIMIT 100
                """
                rows = self._db.execute(sql_fallback, (order_id,)).fetchall()
            except Exception:
                return []

        if not rows:
            return []
        if hasattr(rows[0], "keys"):
            return [dict(r) for r in rows]
        keys = [
            "item_id", "product_id", "product_name",
            "requested_quantity", "actual_quantity",
            "unidad", "available_stock",
        ]
        return [dict(zip(keys, r)) for r in rows]

    def _build_order_dto(self, raw: dict[str, Any]) -> DeliveryOrderViewDTO | None:
        """Convert a raw DB row dict to a typed DeliveryOrderViewDTO."""
        try:
            order_id = str(raw["id"] or "")
            status = _map_legacy_status(raw.get("estado"))
            fulfillment_type = _map_legacy_fulfillment(raw.get("delivery_type"))
            payment_status = _map_payment_status(raw)
            has_driver = bool(raw.get("driver_id"))

            available_actions = _ACTION_POLICY.available_actions(
                status=status,
                fulfillment_type=fulfillment_type,
                payment_status=payment_status,
                has_driver=has_driver,
            )

            items_raw = self._fetch_items(raw["id"])
            items = tuple(self._build_item_dto(i) for i in items_raw)

            driver_id = raw.get("driver_id")
            driver_id_str = str(driver_id) if driver_id is not None else None

            return DeliveryOrderViewDTO(
                order_id=order_id,
                folio=str(raw.get("folio") or ""),
                branch_id=str(raw.get("branch_id") or ""),
                customer_name=str(raw.get("customer_name") or ""),
                customer_tel=str(raw.get("customer_tel") or ""),
                fulfillment_type=fulfillment_type,
                status=status,
                status_label_es=STATUS_LABELS_ES.get(status, str(status)),
                payment_status=payment_status,
                driver_id=driver_id_str,
                driver_name=str(raw.get("driver_name") or "") or None,
                items=items,
                available_actions=available_actions,
                created_at=str(raw.get("created_at") or ""),
                total=Decimal(str(raw.get("total") or 0)),
            )
        except Exception as exc:
            logger.exception(
                "Failed to build DeliveryOrderViewDTO for order %s: %s",
                raw.get("id"), exc,
            )
            return None

    # ── Auxiliary read methods for the UI detail panel ───────────────────────

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the DB."""
        try:
            row = self._db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
                (table_name,),
            ).fetchone()
            return bool(row)
        except Exception:
            return False

    def columns_of(self, table_name: str) -> list[str]:
        """Return column names for a table."""
        try:
            return [r[1] for r in self._db.execute(
                f"PRAGMA table_info({table_name})"
            ).fetchall()]
        except Exception:
            return []

    def load_order_items(
        self, order_id: Any, sale_id: Any = None
    ) -> list[tuple]:
        """Load delivery items with safe fallback to sale items."""
        try:
            if self.table_exists("delivery_items"):
                cols = set(self.columns_of("delivery_items"))
                prepared_expr = (
                    "COALESCE(prepared_qty, cantidad)" if "prepared_qty" in cols else "cantidad"
                )
                adjustment_expr = (
                    "COALESCE(adjustment_status, '')" if "adjustment_status" in cols else "''"
                )
                rows = self._db.execute(
                    f"SELECT nombre, cantidad AS requested_qty, {prepared_expr} AS prepared_qty, "
                    f"precio_unitario, subtotal, {adjustment_expr} AS adjustment_status "
                    f"FROM delivery_items WHERE delivery_id=? ORDER BY id LIMIT 50",
                    (order_id,),
                ).fetchall()
                if rows:
                    return rows
        except Exception as exc:
            logger.warning("load_order_items: order=%s: %s", order_id, exc)

        if sale_id:
            try:
                if self.table_exists("detalles_venta"):
                    rows = self._db.execute(
                        "SELECT COALESCE(p.nombre, dv.producto_nombre, 'Producto'), dv.cantidad, dv.cantidad, "
                        "COALESCE(dv.precio_unitario, 0), COALESCE(dv.subtotal, 0), '' "
                        "FROM detalles_venta dv "
                        "LEFT JOIN productos p ON p.id = dv.producto_id "
                        "WHERE dv.venta_id=? LIMIT 50",
                        (sale_id,),
                    ).fetchall()
                    if rows:
                        return rows
                if self.table_exists("venta_items"):
                    rows = self._db.execute(
                        "SELECT COALESCE(vi.producto_nombre, 'Producto'), vi.cantidad, vi.cantidad, "
                        "COALESCE(vi.precio_unitario, 0), COALESCE(vi.subtotal, 0), '' "
                        "FROM venta_items vi WHERE vi.venta_id=? LIMIT 50",
                        (sale_id,),
                    ).fetchall()
                    if rows:
                        return rows
            except Exception as exc:
                logger.warning("load_order_items fallback: sale=%s: %s", sale_id, exc)
        return []

    def load_order_history(self, order_id: Any, current_status: str = "") -> str:
        """Load order status history with safe fallback."""
        try:
            if self.table_exists("delivery_order_history"):
                rows = self._db.execute(
                    "SELECT estado_anterior, estado_nuevo, usuario, fecha, observacion "
                    "FROM delivery_order_history WHERE order_id=? ORDER BY fecha ASC LIMIT 40",
                    (order_id,),
                ).fetchall()
                if rows:
                    lines = []
                    for prev_s, new_s, user, when, note in rows:
                        parts = [str(when or "")[:19], f"{prev_s or '-'} → {new_s or '-'}"]
                        if user:
                            parts.append(f"por {user}")
                        if note:
                            parts.append(str(note))
                        lines.append(" · ".join(parts))
                    return "\n".join(lines)
        except Exception as exc:
            logger.warning("load_order_history (new table) order=%s: %s", order_id, exc)
        try:
            if self.table_exists("delivery_status_events"):
                rows = self._db.execute(
                    "SELECT to_status, created_at, note FROM delivery_status_events "
                    "WHERE order_id=? ORDER BY created_at ASC LIMIT 40",
                    (order_id,),
                ).fetchall()
                if rows:
                    return "\n".join([
                        f"{str(r[1])[:19]} · {r[0]}{(' · ' + str(r[2])) if r[2] else ''}"
                        for r in rows
                    ])
        except Exception as exc:
            logger.warning("load_order_history (legacy table) order=%s: %s", order_id, exc)
        return f"Creado\nEstado actual · {current_status}"

    def load_whatsapp_conversation(self, order_id: Any, pedido: dict[str, Any]) -> str:
        """Load WhatsApp conversation for an order with fallback."""
        try:
            if self.table_exists("whatsapp_messages"):
                cols = set(self.columns_of("whatsapp_messages"))
                if {"pedido_id", "mensaje", "tipo", "fecha"}.issubset(cols):
                    rows = self._db.execute(
                        "SELECT mensaje, tipo, fecha FROM whatsapp_messages "
                        "WHERE pedido_id=? ORDER BY fecha ASC LIMIT 12",
                        (order_id,),
                    ).fetchall()
                    if rows:
                        lines = []
                        for msg_text, msg_tipo, msg_fecha in rows:
                            is_out = str(msg_tipo or "").lower() in ("enviado", "out", "bot", "sistema")
                            prefix = "→" if is_out else "←"
                            hora = str(msg_fecha or "")[-8:][:5]
                            lines.append(f"[{hora}] {prefix} {msg_text}")
                        return "\n".join(lines)
        except Exception as exc:
            logger.warning("load_whatsapp_conversation order=%s: %s", order_id, exc)
        wa_id = pedido.get("whatsapp_order_id") or ""
        snippet = (pedido.get("notas") or "")[:80]
        if wa_id:
            return f"Pedido WA #{wa_id}\n{snippet}" if snippet else f"Pedido WA #{wa_id}"
        return "Sin conversación registrada en ERP"

    def count_pending_whatsapp_sales(self) -> int:
        """Count pending WhatsApp sales that haven't been imported to delivery."""
        try:
            if not self.table_exists("ventas"):
                return 0
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(ventas)").fetchall()}
            if "id" not in cols:
                return 0
            where = ["1=1"]
            if "canal" in cols:
                where.append("lower(canal)='whatsapp'")
            if "estado" in cols:
                where.append(
                    "lower(estado) IN ('pendiente','pendiente_wa','en_preparacion',"
                    "'preparacion','en_ruta','programado')"
                )
            return int(
                self._db.execute(
                    f"SELECT COUNT(*) FROM ventas WHERE {' AND '.join(where)}"
                ).fetchone()[0] or 0
            )
        except Exception:
            return 0

    def get_order_raw(self, order_id: Any) -> dict[str, Any] | None:
        """Fetch a single order row as a dict (for detail dialog read-only display)."""
        try:
            row = self._db.execute(
                "SELECT * FROM delivery_orders WHERE id=?", (order_id,)
            ).fetchone()
            if row is None:
                return None
            if hasattr(row, "keys"):
                return dict(row)
            # Positional — return as-is via description
            desc = self._db.execute(
                "SELECT * FROM delivery_orders WHERE id=?", (order_id,)
            )
            cols = [d[0] for d in desc.description]
            return dict(zip(cols, row))
        except Exception as exc:
            logger.warning("get_order_raw order=%s: %s", order_id, exc)
            return None

    def get_driver_locations(self) -> list[dict[str, Any]]:
        """Load driver GPS locations for map display."""
        try:
            rows = self._db.execute(
                "SELECT c.nombre, dl.lat, dl.lng, dl.actualizado "
                "FROM driver_locations dl "
                "JOIN empleados c ON c.id = dl.chofer_id "
                "ORDER BY dl.actualizado DESC"
            ).fetchall()
            return [
                {"name": r[0], "lat": float(r[1] or 20.967), "lng": float(r[2] or -89.623)}
                for r in rows
            ]
        except Exception:
            return []

    def get_order_total(self, order_id: Any) -> float:
        """Fetch the total amount for an order."""
        try:
            row = self._db.execute(
                "SELECT COALESCE(total, 0) FROM delivery_orders WHERE id=?", (order_id,)
            ).fetchone()
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def get_notification_inbox(
        self, branch_id: Any, last_rowid: int, limit: int = 30
    ) -> list[tuple]:
        """Fetch unread delivery notifications from inbox."""
        try:
            return self._db.execute(
                "SELECT id, titulo, mensaje, tipo, dedupe_key, order_id "
                "FROM notification_inbox "
                "WHERE COALESCE(sucursal_id,1)=? AND COALESCE(leido,0)=0 "
                "AND id>? "
                "ORDER BY id ASC LIMIT ?",
                (branch_id, int(last_rowid or 0), limit),
            ).fetchall()
        except Exception:
            return []

    def search_customers(self, query: str, limit: int = 12) -> list[tuple]:
        """Search customers by name or phone."""
        try:
            return self._db.execute(
                "SELECT id, nombre, COALESCE(telefono,''), COALESCE(direccion,'')"
                " FROM clientes WHERE (nombre LIKE ? OR telefono LIKE ?) AND activo=1"
                " ORDER BY nombre LIMIT ?",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        except Exception:
            return []

    def search_products(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search products by name or code."""
        try:
            from backend.application.queries.product_query_service import ProductQueryService
            svc = ProductQueryService(self._db)
            results = svc.search_products(query)
            return [
                {
                    "id": r.get("id"),
                    "nombre": r.get("nombre") or r.get("name", ""),
                    "precio": float(r.get("precio") or r.get("price") or 0),
                    "unidad": r.get("unidad") or r.get("unit") or "",
                }
                for r in results
            ]
        except Exception:
            try:
                raw = self._db.execute(
                    "SELECT id, nombre, COALESCE(precio,0), COALESCE(unidad,'')"
                    " FROM productos WHERE (nombre LIKE ? OR codigo LIKE ?) AND activo=1"
                    " ORDER BY nombre LIMIT ?",
                    (f"%{query}%", f"%{query}%", limit),
                ).fetchall()
                return [
                    {"id": r[0], "nombre": r[1], "precio": float(r[2] or 0), "unidad": r[3]}
                    for r in raw
                ]
            except Exception:
                return []

    def get_driver_cut_history(self, limit: int = 100) -> list[tuple]:
        """Return driver settlement cut history rows."""
        try:
            return self._db.execute("""
                SELECT id, driver_nombre,
                       COALESCE(fecha, turno_fin, datetime('now')) AS fecha,
                       entregas_total,
                       efectivo_cobrado, tarjeta_cobrado, transfer_cobrado,
                       efectivo_entregado, diferencia, usuario_corte
                FROM delivery_driver_cuts
                ORDER BY COALESCE(fecha, turno_fin) DESC LIMIT ?
            """, (limit,)).fetchall()
        except Exception:
            return []

    def get_active_drivers(self) -> list[tuple]:
        """Return active drivers for the cut dialog."""
        try:
            return self._db.execute(
                "SELECT id, nombre FROM drivers WHERE activo=1 ORDER BY nombre"
            ).fetchall()
        except Exception:
            return []

    # ── Internal item builder ─────────────────────────────────────────────────

    def _build_item_dto(self, raw: dict[str, Any]) -> DeliveryItemViewDTO:
        """Convert a raw item row to a typed DeliveryItemViewDTO."""
        unit_code = _map_legacy_unit(raw.get("unidad"))
        unit_label = UNIT_LABELS_ES.get(unit_code, str(unit_code.value))
        actual_qty_raw = raw.get("actual_quantity")
        actual_qty = Decimal(str(actual_qty_raw)) if actual_qty_raw is not None else None

        return DeliveryItemViewDTO(
            item_id=str(raw.get("item_id") or ""),
            product_id=str(raw.get("product_id") or ""),
            product_name=str(raw.get("product_name") or ""),
            requested_quantity=Decimal(str(raw.get("requested_quantity") or 0)),
            actual_quantity=actual_qty,
            unit_code=unit_code,
            unit_label_es=unit_label,
            allows_weight_adjustment=unit_code in WEIGHABLE_UNITS,
            available_stock=Decimal(str(raw.get("available_stock") or 0)),
        )

    # ── Auto-assignment helper ──────────────────────────────────────────────

    def get_pending_unassigned_order_ids(self, branch_id: str) -> list[str]:
        """Return IDs of pending delivery orders with no driver assigned."""
        try:
            rows = self._conn.execute(
                "SELECT id FROM delivery_orders "
                "WHERE estado='pendiente' AND driver_id IS NULL "
                "AND sucursal_id=? ORDER BY fecha_solicitud",
                (branch_id,),
            ).fetchall()
            return [str(r[0]) for r in rows]
        except Exception:
            logger.exception("get_pending_unassigned_order_ids failed")
            return []
