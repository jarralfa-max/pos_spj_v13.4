# api/routers/ordenes_compra.py — Órdenes de compra automáticas desde WA
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from api.deps import get_db
from api.auth import verify_api_key

router = APIRouter(prefix="/ordenes-compra", tags=["ordenes-compra"])


# ── Models ────────────────────────────────────────────────────────────────────

class OrdenCompraIn(BaseModel):
    producto_id:  int
    cantidad:     float = Field(gt=0)
    sucursal_id:  int   = 1
    proveedor_id: Optional[int] = None
    notas:        str   = "OC automática desde WA"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def crear_orden_compra(
    body: OrdenCompraIn,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """
    Crea una orden de compra para reponer stock insuficiente.
    Compatible con ambos esquemas de ordenes_compra (m000 y standalone/050).
    """
    prod = db.execute(
        "SELECT nombre, COALESCE(proveedor_id, 0) as proveedor_id "
        "FROM productos WHERE id=?",
        (body.producto_id,)
    ).fetchone()
    if not prod:
        raise HTTPException(404, f"Producto {body.producto_id} no encontrado")

    proveedor_id = body.proveedor_id or (prod[1] if prod[1] else None)

    try:
        from backend.shared.ids import new_uuid
        oc_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        # Intentar insertar con esquema extendido (tiene sucursal_id)
        db.execute("""
            INSERT INTO ordenes_compra (
                id, producto_id, proveedor_id, cantidad,
                estado, sucursal_id, notas, fecha_creacion
            ) VALUES (?, ?, ?, ?, 'pendiente', ?, ?, datetime('now'))
        """, (oc_id, body.producto_id, proveedor_id, body.cantidad,
              body.sucursal_id, body.notas))
        db.commit()
        return {
            "ok": True,
            "orden_id": oc_id,
            "producto_id": body.producto_id,
            "producto_nombre": prod[0],
            "cantidad": body.cantidad,
            "estado": "pendiente",
        }
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/{orden_id}")
async def get_orden_compra(
    orden_id: int,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Detalle de una orden de compra."""
    row = db.execute(
        "SELECT * FROM ordenes_compra WHERE id=?", (orden_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Orden {orden_id} no encontrada")
    return {"orden": dict(row)}


@router.patch("/{orden_id}/estado")
async def actualizar_estado_oc(
    orden_id: int,
    estado: str,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Actualiza estado de una OC: pendiente → confirmada → recibida → cancelada."""
    ESTADOS = {"pendiente", "confirmada", "recibida", "cancelada"}
    if estado not in ESTADOS:
        raise HTTPException(422, f"Estado inválido. Válidos: {ESTADOS}")
    row = db.execute(
        "SELECT id FROM ordenes_compra WHERE id=?", (orden_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Orden {orden_id} no encontrada")
    db.execute(
        "UPDATE ordenes_compra SET estado=? WHERE id=?", (estado, orden_id)
    )
    db.commit()
    return {"ok": True, "orden_id": orden_id, "estado": estado}
