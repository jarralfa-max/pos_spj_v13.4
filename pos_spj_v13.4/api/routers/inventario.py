# api/routers/inventario.py — Endpoints de inventario
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db, get_container
from api.auth import verify_api_key

router = APIRouter(prefix="/inventario", tags=["inventario"])


class AjusteIn(BaseModel):
    producto_id:   int
    cantidad:      float = Field(ge=0)
    motivo:        str   = ""
    usuario:       str   = "api"
    sucursal_id:   int   = 1


class EntradaIn(BaseModel):
    producto_id:    int
    cantidad:       float = Field(gt=0)
    costo_unitario: float = Field(ge=0)
    referencia:     str   = ""
    usuario:        str   = "api"
    sucursal_id:    int   = 1


@router.get("/stock/{producto_id}")
async def get_stock(
    producto_id: int,
    sucursal_id: int = 0,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Retorna existencia actual de un producto."""
    if sucursal_id:
        row = db.execute(
            "SELECT COALESCE(cantidad, 0) AS stock FROM inventario_actual "
            "WHERE producto_id=? AND sucursal_id=?",
            (producto_id, sucursal_id)
        ).fetchone()
    else:
        row = db.execute(
            "SELECT COALESCE(existencia, 0) AS stock FROM productos WHERE id=?",
            (producto_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, f"Producto {producto_id} no encontrado")
    return {"producto_id": producto_id, "sucursal_id": sucursal_id or "global",
            "stock": float(row["stock"])}


@router.get("")
async def listar_stock(
    sucursal_id: int = 1,
    bajo_minimo: bool = False,
    limit:       int = 100,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Lista stock actual por sucursal, opcionalmente filtrando por bajo mínimo."""
    query = """
        SELECT p.id, p.nombre, p.codigo_barras,
               COALESCE(ia.cantidad, 0) AS stock,
               COALESCE(p.stock_minimo, 0) AS minimo,
               p.precio, p.precio_compra
        FROM productos p
        LEFT JOIN inventario_actual ia
               ON ia.producto_id = p.id AND ia.sucursal_id = ?
        WHERE COALESCE(p.oculto, 0) = 0
    """
    params = [sucursal_id]
    if bajo_minimo:
        query += " AND COALESCE(ia.cantidad, 0) <= COALESCE(p.stock_minimo, 0)"
    query += " ORDER BY p.nombre LIMIT ?"
    params.append(min(limit, 500))
    rows = db.execute(query, params).fetchall()
    return {"sucursal_id": sucursal_id, "productos": [dict(r) for r in rows]}


@router.post("/ajuste")
async def ajustar_stock(
    body: AjusteIn,
    _key: str = Depends(verify_api_key),
    container=Depends(get_container),
):
    """Ajusta stock a un valor exacto. Usa ERPApplicationService."""
    app_svc = getattr(container, "app_service", None)
    if not app_svc:
        raise HTTPException(503, "ERPApplicationService no disponible")
    result = app_svc.registrar_ajuste(
        producto_id=body.producto_id,
        nueva_cantidad=body.cantidad,
        motivo=body.motivo,
        usuario=body.usuario,
        sucursal_id=body.sucursal_id,
    )
    if not result.get("ok"):
        raise HTTPException(422, result.get("error", "Ajuste fallido"))
    return result


@router.post("/entrada")
async def registrar_entrada(
    body: EntradaIn,
    _key: str = Depends(verify_api_key),
    container=Depends(get_container),
):
    """Registra entrada de inventario (compra, devolución, etc.)."""
    app_svc = getattr(container, "app_service", None)
    if not app_svc:
        raise HTTPException(503, "ERPApplicationService no disponible")
    result = app_svc.registrar_compra(
        producto_id=body.producto_id,
        cantidad=body.cantidad,
        costo_unitario=body.costo_unitario,
        usuario=body.usuario,
        referencia=body.referencia,
        sucursal_id=body.sucursal_id,
    )
    if not result.get("ok"):
        raise HTTPException(422, result.get("error", "Entrada fallida"))
    return result


@router.get("/movimientos/{producto_id}")
async def movimientos_producto(
    producto_id: int,
    limit:       int = 50,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Historial de movimientos de un producto."""
    rows = db.execute("""
        SELECT tipo, tipo_movimiento, cantidad, descripcion,
               referencia, usuario, sucursal_id, fecha
        FROM movimientos_inventario
        WHERE producto_id=?
        ORDER BY fecha DESC LIMIT ?
    """, (producto_id, min(limit, 200))).fetchall()
    return {"producto_id": producto_id, "movimientos": [dict(r) for r in rows]}
