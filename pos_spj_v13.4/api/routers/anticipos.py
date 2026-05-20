# api/routers/anticipos.py — Registro y confirmación de anticipos
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db
from api.auth import verify_api_key

router = APIRouter(prefix="/anticipos", tags=["anticipos"])


# ── Models ────────────────────────────────────────────────────────────────────

class AnticipoIn(BaseModel):
    venta_id: int
    monto:    float = Field(gt=0)
    metodo:   str   = "mercadopago"   # mercadopago | efectivo | transferencia


class ConfirmarPagoIn(BaseModel):
    monto:      float = Field(gt=0)
    referencia: str   = ""
    metodo:     str   = "mercadopago"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def registrar_anticipo(
    body: AnticipoIn,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """
    Registra un anticipo pendiente para una venta.
    Crea la tabla si no existe (compatible con despliegues sin migración 050).
    """
    # Garantizar que la tabla existe
    db.execute("""
        CREATE TABLE IF NOT EXISTS anticipos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id    INTEGER NOT NULL,
            monto       REAL    NOT NULL,
            metodo      TEXT    DEFAULT 'mercadopago',
            estado      TEXT    DEFAULT 'pendiente',
            referencia  TEXT    DEFAULT '',
            fecha       TEXT    DEFAULT (datetime('now')),
            fecha_pago  TEXT
        )
    """)

    venta = db.execute(
        "SELECT id, estado FROM ventas WHERE id=?", (body.venta_id,)
    ).fetchone()
    if not venta:
        raise HTTPException(404, f"Venta {body.venta_id} no encontrada")

    try:
        cur = db.execute("""
            INSERT INTO anticipos (venta_id, monto, metodo, estado, fecha)
            VALUES (?, ?, ?, 'pendiente', datetime('now'))
        """, (body.venta_id, body.monto, body.metodo))
        anticipo_id = cur.lastrowid
        db.commit()
        return {
            "ok": True,
            "anticipo_id": anticipo_id,
            "venta_id": body.venta_id,
            "monto": body.monto,
            "estado": "pendiente",
        }
    except Exception as e:
        raise HTTPException(422, str(e))


@router.patch("/{anticipo_id}/confirmar")
async def confirmar_pago(
    anticipo_id: int,
    body: ConfirmarPagoIn,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """
    Confirma el pago de un anticipo y actualiza la venta a 'confirmada'.
    Idempotente: si ya está pagado retorna OK sin error.
    """
    row = db.execute(
        "SELECT id, venta_id, estado FROM anticipos WHERE id=?", (anticipo_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Anticipo {anticipo_id} no encontrado")

    row = dict(row)
    if row["estado"] == "pagado":
        return {"ok": True, "anticipo_id": anticipo_id, "estado": "pagado",
                "message": "ya confirmado (idempotente)"}

    try:
        db.execute("""
            UPDATE anticipos
            SET estado='pagado', fecha_pago=datetime('now'),
                referencia=?, monto=?, metodo=?
            WHERE id=?
        """, (body.referencia, body.monto, body.metodo, anticipo_id))

        db.execute(
            "UPDATE ventas SET estado='confirmada', anticipo_pagado=? WHERE id=?",
            (body.monto, row["venta_id"])
        )
        db.commit()
        return {
            "ok": True,
            "anticipo_id": anticipo_id,
            "venta_id": row["venta_id"],
            "estado": "pagado",
            "monto": body.monto,
        }
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/venta/{venta_id}")
async def anticipos_de_venta(
    venta_id: int,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Lista todos los anticipos de una venta."""
    try:
        rows = db.execute(
            "SELECT * FROM anticipos WHERE venta_id=? ORDER BY fecha",
            (venta_id,)
        ).fetchall()
        return {"anticipos": [dict(r) for r in rows]}
    except Exception:
        return {"anticipos": []}
