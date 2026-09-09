# api/routers/ventas.py — Endpoints de ventas
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import get_db, get_sales_reversal_service, get_uc_venta
from api.auth import verify_api_key

router = APIRouter(prefix="/ventas", tags=["ventas"])


# ── DTOs ──────────────────────────────────────────────────────────────────────

class ItemVentaIn(BaseModel):
    producto_id: str
    cantidad:    float = Field(gt=0)
    precio_unit: float = Field(gt=0)
    nombre:      str   = ""

class VentaIn(BaseModel):
    items:            List[ItemVentaIn]
    forma_pago:       str   = "Efectivo"
    monto_pagado:     float = 0.0
    cliente_id: Optional[str] = None
    descuento_global: float = 0.0
    sucursal_id: str = ""
    usuario:          str   = "api"
    notas:            str   = ""

class VentaOut(BaseModel):
    ok:            bool
    venta_id: str = ""
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
    venta_id: str,
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
    sucursal_id: str = "",
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
    venta_id: str,
    usuario:  str,
    motivo:   str = "",
    _key: str = Depends(verify_api_key),
    reversal=Depends(get_sales_reversal_service),
):
    """Anula (cancela totalmente) una venta completada.

    Adaptador delgado (§19): delega en `SalesReversalService.cancel_sale()`,
    el único punto de entrada de cancelaciones. Antes hacía
    `UPDATE ventas SET estado='cancelada'` con SQL directo, lo que dejaba la
    venta anulada PERO con su asiento contable y su cuenta por cobrar
    vigentes, el inventario sin devolver, la caja sin compensar, los puntos
    de fidelidad sin revertir y sin emitir evento — los libros y el ledger
    de ventas divergían en silencio (§11/§31).

    El servicio hace todo eso en una sola transacción `BEGIN IMMEDIATE`, con
    `operation_id` idempotente y reversa contable vía `finance_service`.

    Cambios de contrato que esto implica, deliberados:
      * `usuario` pasa a ser OBLIGATORIO — es el actor del audit trail, y
        `cancel_sale()` rechaza una cancelación anónima.
      * sólo se cancela una venta en estado `completada`. Antes se aceptaba
        cualquier estado; cancelar una venta no completada por esta vía
        producía un registro incoherente. Los demás estados responden 409.
    """
    from core.services.sales_reversal_service import (
        ReversalError,
        UsuarioRequeridoError,
        VentaNoCompletadaError,
        VentaNoEncontradaError,
        VentaYaCanceladaError,
    )

    try:
        result = reversal.cancel_sale(venta_id, usuario, motivo)
    except VentaNoEncontradaError:
        raise HTTPException(404, f"Venta {venta_id} no encontrada")
    except VentaYaCanceladaError:
        raise HTTPException(409, "La venta ya está anulada")
    except VentaNoCompletadaError as exc:
        raise HTTPException(409, str(exc))
    except UsuarioRequeridoError as exc:
        raise HTTPException(422, str(exc))
    except ReversalError as exc:
        # Falla de negocio conocida del servicio: 409, no 500. La transacción
        # ya hizo rollback completo.
        raise HTTPException(409, str(exc))

    return {
        "ok": True,
        "venta_id": venta_id,
        "estado": "cancelada",
        "operation_id": result.operation_id,
        "total_revertido": result.total_revertido,
        "inventario_restaurado": result.inventario_restaurado,
    }
