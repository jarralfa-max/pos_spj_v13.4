# api/routers/pedidos.py — Endpoints de pedidos (WhatsApp / delivery)
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, get_container
from api.auth import verify_api_key

router = APIRouter(prefix="/pedidos", tags=["pedidos"])


class ItemPedidoIn(BaseModel):
    producto_id:    int
    nombre:         str   = ""
    cantidad:       float = Field(gt=0)
    precio_unitario: float = Field(ge=0)


class PedidoIn(BaseModel):
    cliente_id:      Optional[int] = None
    phone:           str   = ""
    items:           List[ItemPedidoIn]
    tipo_entrega:    str   = "sucursal"   # "sucursal" | "domicilio"
    direccion:       str   = ""
    fecha_entrega:   str   = ""
    notas:           str   = ""
    sucursal_id:     int   = 1
    canal:           str   = "whatsapp"


@router.post("", status_code=201)
async def crear_pedido(
    body: PedidoIn,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """
    Crea un pedido pendiente (venta en estado 'pendiente_wa').
    Usado por el microservicio WhatsApp via REST en lugar de acceso directo a DB.
    """
    import uuid as _uuid

    total = sum(it.cantidad * it.precio_unitario for it in body.items)
    folio = f"WA-{_uuid.uuid4().hex[:8].upper()}"

    try:
        cur = db.execute("""
            INSERT INTO ventas (
                folio, cliente_id, total, subtotal, estado,
                sucursal_id, tipo_entrega, direccion_entrega,
                fecha_entrega_programada, notas, canal, fecha
            ) VALUES (?, ?, ?, ?, 'pendiente_wa', ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (folio, body.cliente_id, total, total, body.sucursal_id,
              body.tipo_entrega, body.direccion, body.fecha_entrega,
              body.notas, body.canal))
        venta_id = cur.lastrowid

        for it in body.items:
            db.execute("""
                INSERT INTO detalles_venta
                    (venta_id, producto_id, nombre, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (venta_id, it.producto_id, it.nombre, it.cantidad,
                  it.precio_unitario, round(it.cantidad * it.precio_unitario, 2)))

        return {
            "ok": True,
            "venta_id": venta_id,
            "folio": folio,
            "total": round(total, 2),
            "estado": "pendiente_wa",
        }
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("")
async def listar_pedidos(
    estado:      str = "pendiente_wa",
    sucursal_id: int = 1,
    limit:       int = 50,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Lista pedidos por estado y sucursal."""
    rows = db.execute("""
        SELECT v.id, v.folio, v.total, v.estado, v.fecha,
               v.tipo_entrega, v.canal,
               c.nombre AS cliente_nombre, c.telefono AS cliente_telefono
        FROM ventas v
        LEFT JOIN clientes c ON c.id = v.cliente_id
        WHERE v.estado=? AND v.sucursal_id=?
        ORDER BY v.fecha DESC LIMIT ?
    """, (estado, sucursal_id, min(limit, 200))).fetchall()
    return {"pedidos": [dict(r) for r in rows]}


@router.get("/{pedido_id}")
async def get_pedido(
    pedido_id: int,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Detalle completo de un pedido con sus líneas."""
    row = db.execute(
        "SELECT v.*, c.nombre AS cliente_nombre, c.telefono AS cliente_telefono "
        "FROM ventas v LEFT JOIN clientes c ON c.id = v.cliente_id WHERE v.id=?",
        (pedido_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Pedido {pedido_id} no encontrado")
    items = db.execute(
        "SELECT producto_id, nombre, cantidad, precio_unitario, subtotal "
        "FROM detalles_venta WHERE venta_id=?",
        (pedido_id,)
    ).fetchall()
    return {"pedido": dict(row), "items": [dict(i) for i in items]}


@router.patch("/{pedido_id}/estado")
async def actualizar_estado_pedido(
    pedido_id: int,
    estado:    str,
    notas:     str = "",
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Actualiza el estado de un pedido (confirmado, en_camino, entregado, cancelado)."""
    ESTADOS_VALIDOS = {"confirmado", "en_camino", "entregado", "cancelado", "pendiente_wa"}
    if estado not in ESTADOS_VALIDOS:
        raise HTTPException(422, f"Estado inválido. Válidos: {ESTADOS_VALIDOS}")
    row = db.execute("SELECT id FROM ventas WHERE id=?", (pedido_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Pedido {pedido_id} no encontrado")
    db.execute(
        "UPDATE ventas SET estado=?, notas=COALESCE(notas,'') || CASE WHEN ? != '' "
        "THEN ' | ' || ? ELSE '' END WHERE id=?",
        (estado, notas, notas, pedido_id)
    )
    return {"ok": True, "pedido_id": pedido_id, "estado": estado}
