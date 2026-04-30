# api/routers/ventas.py — Endpoints de ventas
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import get_db, get_uc_venta
from api.auth import verify_api_key

router = APIRouter(prefix="/ventas", tags=["ventas"])


# ── DTOs ──────────────────────────────────────────────────────────────────────

class ItemVentaIn(BaseModel):
    producto_id: int
    cantidad:    float = Field(gt=0)
    precio_unit: float = Field(gt=0)
    nombre:      str   = ""

class VentaIn(BaseModel):
    items:            List[ItemVentaIn]
    forma_pago:       str   = "Efectivo"
    monto_pagado:     float = 0.0
    cliente_id:       Optional[int] = None
    descuento_global: float = 0.0
    sucursal_id:      int   = 1
    usuario:          str   = "api"
    notas:            str   = ""

class VentaOut(BaseModel):
    ok:            bool
    venta_id:      int   = 0
    folio:         str   = ""
    total:         float = 0.0
    cambio:        float = 0.0
    puntos_ganados: int  = 0
    error:         str   = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
async def crear_venta(
    body: VentaIn,
    _key: str = Depends(verify_api_key),
    uc=Depends(get_uc_venta),
):
    """Procesa una venta completa. Requiere X-API-Key."""
    from core.use_cases.venta import ItemCarrito, DatosPago
    items = [
        ItemCarrito(
            producto_id=it.producto_id,
            cantidad=it.cantidad,
            precio_unit=it.precio_unit,
            nombre=it.nombre,
        )
        for it in body.items
    ]
    datos = DatosPago(
        forma_pago=body.forma_pago,
        monto_pagado=body.monto_pagado,
        cliente_id=body.cliente_id,
        descuento_global=body.descuento_global,
        notas=body.notas,
    )
    resultado = uc.ejecutar(items, datos, body.sucursal_id, body.usuario)
    if not resultado.ok:
        raise HTTPException(status_code=422, detail=resultado.error)
    return VentaOut(
        ok=True,
        venta_id=resultado.venta_id,
        folio=resultado.folio,
        total=resultado.total,
        cambio=resultado.cambio,
        puntos_ganados=resultado.puntos_ganados,
    )


@router.get("/{venta_id}")
async def get_venta(
    venta_id: int,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Retorna los detalles de una venta por ID."""
    row = db.execute(
        "SELECT id, folio, total, estado, fecha, forma_pago, cliente_id, sucursal_id "
        "FROM ventas WHERE id=?", (venta_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Venta {venta_id} no encontrada")
    items = db.execute(
        "SELECT producto_id, cantidad, precio_unitario, subtotal "
        "FROM detalles_venta WHERE venta_id=?", (venta_id,)
    ).fetchall()
    return {
        "venta": dict(row),
        "items": [dict(i) for i in items],
    }


@router.get("")
async def listar_ventas(
    sucursal_id: int = 1,
    limit:       int = 50,
    offset:      int = 0,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Lista ventas recientes de una sucursal."""
    rows = db.execute(
        "SELECT id, folio, total, estado, fecha, forma_pago, cliente_id "
        "FROM ventas WHERE sucursal_id=? ORDER BY fecha DESC LIMIT ? OFFSET ?",
        (sucursal_id, min(limit, 200), offset)
    ).fetchall()
    return {"ventas": [dict(r) for r in rows], "limit": limit, "offset": offset}


@router.post("/{venta_id}/anular")
async def anular_venta(
    venta_id: int,
    motivo:   str = "",
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Anula una venta existente."""
    from fastapi import Request
    from core.services.sales_service import SalesService
    # Obtener sales_service del container
    row = db.execute("SELECT estado FROM ventas WHERE id=?", (venta_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Venta {venta_id} no encontrada")
    if row["estado"] in ("cancelada", "anulada"):
        raise HTTPException(409, "La venta ya está anulada")
    try:
        # Usar sales_service si está disponible en el scope
        db.execute(
            "UPDATE ventas SET estado='cancelada', notas=? WHERE id=?",
            (motivo, venta_id)
        )
        return {"ok": True, "venta_id": venta_id, "estado": "cancelada"}
    except Exception as e:
        raise HTTPException(500, str(e))
