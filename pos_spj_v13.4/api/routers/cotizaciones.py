# api/routers/cotizaciones.py — CRUD cotizaciones + conversión a venta
from __future__ import annotations
import uuid as _uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db
from api.auth import verify_api_key
from backend.shared.ids import new_uuid

router = APIRouter(prefix="/cotizaciones", tags=["cotizaciones"])


# ── Request / Response models ─────────────────────────────────────────────────

class ItemCotizacionIn(BaseModel):
    # Identidad UUIDv7 string (REGLA CERO): la API transporta UUIDs.
    producto_id:     str
    nombre:          str   = ""
    cantidad:        float = Field(gt=0)
    precio_unitario: float = Field(ge=0)
    descuento:       float = 0.0


class CotizacionIn(BaseModel):
    cliente_id:   str
    items:        List[ItemCotizacionIn]
    sucursal_id:  str   = ""
    usuario:      str   = "whatsapp"
    notas:        str   = ""
    vigencia_dias: int  = 7


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def crear_cotizacion(
    body: CotizacionIn,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """
    Crea una cotización desde WhatsApp (o cualquier canal).
    Retorna cotizacion_id, folio y total.
    """
    folio = f"CWA-{_uuid.uuid4().hex[:6].upper()}"
    total = sum(
        it.cantidad * it.precio_unitario * (1 - it.descuento / 100)
        for it in body.items
    )

    try:
        # Obtener nombre del cliente
        cliente_row = db.execute(
            "SELECT nombre FROM clientes WHERE id=?", (body.cliente_id,)
        ).fetchone()
        cliente_nombre = cliente_row[0] if cliente_row else ""

        # Identidad UUIDv7 acuñada en aplicación — nunca lastrowid.
        cot_id = new_uuid()
        db.execute("""
            INSERT INTO cotizaciones (
                id, folio, cliente_id, cliente_nombre, subtotal, total,
                estado, usuario, sucursal_id, notas, vigencia_dias,
                fecha_vencimiento, fecha
            ) VALUES (?, ?, ?, ?, ?, ?, 'pendiente', ?, ?, ?, ?,
                      date('now', '+' || ? || ' days'), datetime('now'))
        """, (cot_id, folio, body.cliente_id, cliente_nombre, total, total,
              body.usuario, body.sucursal_id, body.notas,
              body.vigencia_dias, body.vigencia_dias))

        for it in body.items:
            subtotal = round(
                it.cantidad * it.precio_unitario * (1 - it.descuento / 100), 2)
            db.execute("""
                INSERT INTO cotizaciones_detalle (
                    id, cotizacion_id, producto_id, nombre,
                    cantidad, precio_unitario, subtotal, descuento
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (new_uuid(), cot_id, it.producto_id, it.nombre,
                  it.cantidad, it.precio_unitario, subtotal, it.descuento))

        db.commit()
        return {
            "ok": True,
            "cotizacion_id": cot_id,
            "folio": folio,
            "total": round(total, 2),
            "estado": "pendiente",
        }
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/{cotizacion_id}")
async def get_cotizacion(
    cotizacion_id: str,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Detalle de una cotización con sus líneas."""
    row = db.execute(
        "SELECT * FROM cotizaciones WHERE id=?", (cotizacion_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Cotización {cotizacion_id} no encontrada")
    items = db.execute(
        "SELECT producto_id, nombre, cantidad, precio_unitario, subtotal, descuento "
        "FROM cotizaciones_detalle WHERE cotizacion_id=?",
        (cotizacion_id,)
    ).fetchall()
    return {"cotizacion": dict(row), "items": [dict(i) for i in items]}


@router.patch("/{cotizacion_id}/convertir", status_code=200)
async def convertir_a_venta(
    cotizacion_id: str,
    usuario: str = "whatsapp",
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """
    Convierte una cotización pendiente en venta (estado pendiente_wa).
    Retorna venta_id y folio de la venta generada.
    """
    cot = db.execute(
        "SELECT * FROM cotizaciones WHERE id=? AND estado='pendiente'",
        (cotizacion_id,)
    ).fetchone()
    if not cot:
        raise HTTPException(404, "Cotización no encontrada o ya procesada")

    cot = dict(cot)
    items = db.execute(
        "SELECT * FROM cotizaciones_detalle WHERE cotizacion_id=?",
        (cotizacion_id,)
    ).fetchall()
    if not items:
        raise HTTPException(422, "Cotización sin líneas")

    folio = f"WA-{_uuid.uuid4().hex[:8].upper()}"
    total = cot["total"]

    try:
        venta_id = new_uuid()
        db.execute("""
            INSERT INTO ventas (
                id, folio, cliente_id, total, subtotal, estado,
                sucursal_id, tipo_entrega, canal, fecha
            ) VALUES (?, ?, ?, ?, ?, 'pendiente_wa', ?, 'sucursal', 'whatsapp', datetime('now'))
        """, (venta_id, folio, cot["cliente_id"], total, total,
              cot.get("sucursal_id") or ""))

        for it in items:
            it = dict(it)
            db.execute("""
                INSERT INTO detalles_venta (
                    id, venta_id, producto_id, nombre,
                    cantidad, precio_unitario, subtotal
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (new_uuid(), venta_id, it["producto_id"], it["nombre"],
                  it["cantidad"], it["precio_unitario"], it["subtotal"]))

        db.execute(
            "UPDATE cotizaciones SET estado='convertida', venta_ref_id=? WHERE id=?",
            (venta_id, cotizacion_id)
        )
        db.commit()
        return {
            "ok": True,
            "venta_id": venta_id,
            "folio": folio,
            "total": round(total, 2),
            "cotizacion_id": cotizacion_id,
        }
    except Exception as e:
        raise HTTPException(422, str(e))
