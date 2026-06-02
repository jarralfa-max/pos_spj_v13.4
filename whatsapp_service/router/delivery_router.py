# router/delivery_router.py — Endpoints de consulta delivery / pedidos WA
"""
Endpoints usados por el ERP/POS para consultar pedidos entrantes desde WhatsApp.

Este router no envía mensajes a Meta. Solo expone lectura/sincronización de
pedidos creados por el flujo conversacional para que el POS pueda mostrarlos y
actualizar su ciclo de vida.

Contrato importante para el ERP:
- Cada pedido debe incluir `whatsapp_order_id` estable para deduplicar.
- Cada pedido debe incluir `venta_id`, cliente, teléfono, dirección e items.
- /orders/pending solo entrega pedidos NUEVOS de WhatsApp.
- /orders/status permite que Delivery sincronice cambios de estado sin 404.
"""
from __future__ import annotations

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Query, Header, HTTPException
from pydantic import BaseModel

from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService

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


def _resolve_internal_key() -> str:
    try:
        from config.settings import get_internal_api_key
        return get_internal_api_key() or ""
    except Exception:
        try:
            from config.settings import WA_INTERNAL_API_KEY, INTERNAL_API_KEY
            return WA_INTERNAL_API_KEY or INTERNAL_API_KEY or ""
        except Exception:
            return ""


def _check_internal_key(x_internal_key: Optional[str]) -> None:
    internal_key = _resolve_internal_key()
    if not internal_key:
        logger.warning("Internal API key not configured — delivery status endpoint unprotected in dev mode.")
        return
    if not x_internal_key or x_internal_key != internal_key:
        logger.warning("delivery_router: unauthorized request — bad X-Internal-Key")
        raise HTTPException(status_code=403, detail="Unauthorized")


class DeliveryStatusRequest(BaseModel):
    whatsapp_order_id: str
    status: str
    venta_id: Optional[int] = None
    notes: str = ""


def _map_status_to_venta(status: str) -> str:
    st = (status or "").strip().lower()
    return {
        "pendiente": "pendiente_wa",
        "preparacion": "en_preparacion",
        "en_preparacion": "en_preparacion",
        "en_ruta": "en_ruta",
        "entregado": "entregada",
        "entregada": "entregada",
        "cancelado": "cancelada",
        "cancelada": "cancelada",
    }.get(st, st)


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


@router.post("/orders/status")
async def sync_order_status(req: DeliveryStatusRequest,
                            x_internal_key: Optional[str] = Header(None)):
    """Sincroniza estado de Delivery hacia ventas WhatsApp sin generar mensajes repetidos."""
    _check_internal_key(x_internal_key)
    conn = _connect()
    try:
        status_venta = _map_status_to_venta(req.status)
        venta_id = req.venta_id
        if not venta_id and req.whatsapp_order_id.startswith("venta:"):
            try:
                venta_id = int(req.whatsapp_order_id.split(":", 1)[1])
            except Exception:
                venta_id = None

        if not venta_id:
            row = conn.execute(
                "SELECT venta_id FROM delivery_orders WHERE whatsapp_order_id=? LIMIT 1",
                (req.whatsapp_order_id,),
            ).fetchone()
            venta_id = int(row[0]) if row and row[0] else None

        if not venta_id:
            return {"ok": False, "error": "venta_id not found"}

        cols = _table_columns(conn, "ventas")
        if "estado" not in cols:
            return {"ok": False, "error": "ventas.estado not found"}

        projected = SaleDeliveryProjectionService(conn).project_status(venta_id, req.status)
        if not projected:
            return {"ok": False, "error": "delivery sale status projection failed"}
        status_venta = _map_status_to_venta(req.status)
        try:
            conn.execute("""
                INSERT INTO wa_event_log(event_type, data_json, sucursal_id, prioridad, timestamp)
                SELECT 'DELIVERY_STATUS_SYNC',
                       json_object('venta_id', id, 'whatsapp_order_id', ?, 'status', ?, 'estado_venta', ?),
                       COALESCE(sucursal_id,1), 20, datetime('now')
                FROM ventas WHERE id=?
            """, (req.whatsapp_order_id, req.status, status_venta, venta_id))
        except Exception:
            pass
        conn.commit()
        return {"ok": True, "venta_id": venta_id, "estado": status_venta}
    except Exception as exc:
        logger.exception("sync_order_status failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    finally:
        conn.close()
