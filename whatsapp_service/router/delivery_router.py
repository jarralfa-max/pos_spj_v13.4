# router/delivery_router.py — Endpoints de consulta delivery / pedidos WA
"""
Endpoints usados por el ERP/POS para consultar pedidos entrantes desde WhatsApp.

Este router no envía mensajes a Meta. Solo expone lectura de pedidos pendientes
creados por el flujo conversacional para que el POS pueda notificarlos/mostrarlos.

Contrato importante para el ERP:
- Cada pedido debe incluir `whatsapp_order_id` estable para deduplicar.
- Cada pedido debe incluir `venta_id`, cliente, teléfono, dirección e items.
- Este endpoint solo entrega pedidos NUEVOS de WhatsApp. No debe devolver
  confirmados/en preparación/en ruta, porque eso provoca recargas/duplicados
  en el módulo Delivery.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger("wa.delivery")
router = APIRouter(prefix="/api/delivery", tags=["delivery"])


def _connect() -> sqlite3.Connection:
    from config.settings import ERP_DB_PATH
    conn = sqlite3.connect(ERP_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


@router.get("/orders/pending")
async def pending_orders(
    sucursal_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Devuelve pedidos WhatsApp nuevos/pendientes para importar a Delivery."""
    conn = _connect()
    try:
        ventas_cols = _table_columns(conn, "ventas")
        detalle_cols = _table_columns(conn, "detalles_venta")
        clientes_cols = _table_columns(conn, "clientes")

        if not ventas_cols:
            return {"ok": False, "orders": [], "error": "Tabla ventas no existe"}

        has_canal = "canal" in ventas_cols
        has_tipo = "tipo_entrega" in ventas_cols
        has_dir = "direccion_entrega" in ventas_cols
        has_fecha_prog = "fecha_entrega_programada" in ventas_cols
        has_notas = "notas" in ventas_cols
        has_obs = "observations" in ventas_cols
        has_cliente_tel = "telefono" in clientes_cols
        has_cliente_nombre = "nombre" in clientes_cols

        select_parts = [
            "v.id AS venta_id",
            "v.id",
            "'venta:' || v.id AS whatsapp_order_id",
            "'venta:' || v.id AS order_id",
            "COALESCE(v.folio, '') AS folio",
            "v.cliente_id",
            "COALESCE(v.total, 0) AS total",
            "COALESCE(v.estado, '') AS estado",
            "COALESCE(v.sucursal_id, 1) AS sucursal_id",
            "COALESCE(v.fecha, '') AS fecha",
        ]
        select_parts.append("COALESCE(c.nombre, '') AS cliente_nombre" if has_cliente_nombre else "'' AS cliente_nombre")
        select_parts.append("COALESCE(c.nombre, '') AS cliente" if has_cliente_nombre else "'' AS cliente")
        select_parts.append("COALESCE(c.telefono, '') AS cliente_telefono" if has_cliente_tel else "'' AS cliente_telefono")
        select_parts.append("COALESCE(c.telefono, '') AS cliente_tel" if has_cliente_tel else "'' AS cliente_tel")
        select_parts.append("COALESCE(c.telefono, '') AS telefono" if has_cliente_tel else "'' AS telefono")
        select_parts.append("COALESCE(v.canal, 'pos') AS canal" if has_canal else "'pos' AS canal")
        select_parts.append("COALESCE(v.tipo_entrega, 'sucursal') AS tipo_entrega" if has_tipo else "'sucursal' AS tipo_entrega")
        select_parts.append("COALESCE(v.direccion_entrega, '') AS direccion_entrega" if has_dir else "'' AS direccion_entrega")
        select_parts.append("COALESCE(v.direccion_entrega, '') AS direccion" if has_dir else "'' AS direccion")
        select_parts.append("COALESCE(v.fecha_entrega_programada, '') AS fecha_entrega_programada" if has_fecha_prog else "'' AS fecha_entrega_programada")
        if has_notas:
            select_parts.append("COALESCE(v.notas, '') AS notas")
        elif has_obs:
            select_parts.append("COALESCE(v.observations, '') AS notas")
        else:
            select_parts.append("'' AS notas")

        # IMPORTANTE: solo pedidos nuevos desde WA. Estados posteriores se manejan
        # dentro de delivery_orders; no deben volver a importarse como pendientes.
        where = ["COALESCE(v.estado, '') IN ('pendiente_wa')"]
        params: list = []
        if has_canal:
            where.append("COALESCE(v.canal, '') = 'whatsapp'")
        if sucursal_id is not None:
            where.append("COALESCE(v.sucursal_id, 1) = ?")
            params.append(sucursal_id)

        sql = f"""
            SELECT {', '.join(select_parts)}
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            WHERE {' AND '.join(where)}
            ORDER BY datetime(v.fecha) DESC, v.id DESC
            LIMIT ?
        """
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()

        orders = []
        for row in rows:
            order = dict(row)
            detail_select = [
                "d.id",
                "d.producto_id",
                "COALESCE(d.cantidad, 0) AS cantidad",
                "COALESCE(d.precio_unitario, 0) AS precio_unitario",
                "COALESCE(d.precio_unitario, 0) AS precio",
                "COALESCE(d.subtotal, 0) AS subtotal",
            ]
            if "nombre" in detalle_cols:
                detail_select.append("COALESCE(NULLIF(d.nombre,''), p.nombre, 'Producto') AS nombre")
            else:
                detail_select.append("COALESCE(p.nombre, 'Producto') AS nombre")
            if "unidad" in detalle_cols:
                detail_select.append("COALESCE(NULLIF(d.unidad,''), p.unidad, 'kg') AS unidad")
            else:
                detail_select.append("COALESCE(p.unidad, 'kg') AS unidad")

            items = conn.execute(f"""
                SELECT {', '.join(detail_select)}
                FROM detalles_venta d
                LEFT JOIN productos p ON p.id = d.producto_id
                WHERE d.venta_id=?
                ORDER BY d.id
            """, (order["venta_id"],)).fetchall()
            order["items"] = [dict(i) for i in items]
            order["items_count"] = len(order["items"])
            orders.append(order)

        return {"ok": True, "orders": orders, "count": len(orders)}
    except Exception as exc:
        logger.exception("pending_orders failed: %s", exc)
        return {"ok": False, "orders": [], "error": str(exc)}
    finally:
        conn.close()
