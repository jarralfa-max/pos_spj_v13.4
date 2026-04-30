# api/routers/clientes.py — Endpoints de clientes
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db
from api.auth import verify_api_key

router = APIRouter(prefix="/clientes", tags=["clientes"])


class ClienteIn(BaseModel):
    nombre:   str
    telefono: str   = ""
    email:    str   = ""
    direccion: str  = ""
    rfc:      str   = ""


@router.get("")
async def buscar_clientes(
    q:           str = Query("", description="Nombre o teléfono"),
    limit:       int = 20,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Busca clientes por nombre o teléfono."""
    if q:
        rows = db.execute(
            "SELECT id, nombre, telefono, email, puntos, nivel "
            "FROM clientes WHERE (nombre LIKE ? OR telefono LIKE ?) AND activo=1 "
            "ORDER BY nombre LIMIT ?",
            (f"%{q}%", f"%{q}%", min(limit, 100))
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, nombre, telefono, email, puntos, nivel "
            "FROM clientes WHERE activo=1 ORDER BY nombre LIMIT ?",
            (min(limit, 100),)
        ).fetchall()
    return {"clientes": [dict(r) for r in rows]}


@router.get("/{cliente_id}")
async def get_cliente(
    cliente_id: int,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Retorna datos completos de un cliente."""
    row = db.execute(
        "SELECT id, nombre, telefono, email, direccion, rfc, "
        "puntos, nivel, activo, fecha_registro "
        "FROM clientes WHERE id=?", (cliente_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Cliente {cliente_id} no encontrado")

    # Últimas ventas del cliente
    ventas = db.execute(
        "SELECT id, folio, total, fecha, estado FROM ventas "
        "WHERE cliente_id=? ORDER BY fecha DESC LIMIT 10",
        (cliente_id,)
    ).fetchall()

    # Saldo de puntos
    puntos_row = db.execute(
        "SELECT COALESCE(SUM(delta), 0) AS saldo "
        "FROM loyalty_ledger WHERE cliente_id=? AND tipo='credito'",
        (cliente_id,)
    ).fetchone()

    return {
        "cliente": dict(row),
        "ultimas_ventas": [dict(v) for v in ventas],
        "saldo_puntos": float(puntos_row["saldo"]) if puntos_row else float(row["puntos"] or 0),
    }


@router.post("", status_code=201)
async def crear_cliente(
    body: ClienteIn,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Crea un nuevo cliente."""
    existing = db.execute(
        "SELECT id FROM clientes WHERE telefono=? AND activo=1",
        (body.telefono,)
    ).fetchone()
    if existing and body.telefono:
        raise HTTPException(409, f"Ya existe cliente con teléfono {body.telefono}")
    try:
        import uuid as _uuid
        cur = db.execute(
            "INSERT INTO clientes (nombre, telefono, email, direccion, rfc, "
            "codigo_qr, activo, puntos, nivel, fecha_registro) "
            "VALUES (?,?,?,?,?,?,1,0,'Bronce',datetime('now'))",
            (body.nombre, body.telefono, body.email,
             body.direccion, body.rfc, str(_uuid.uuid4())[:12])
        )
        return {"ok": True, "cliente_id": cur.lastrowid, "nombre": body.nombre}
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/{cliente_id}/puntos")
async def get_puntos(
    cliente_id: int,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Retorna historial y saldo de puntos de fidelidad."""
    row = db.execute(
        "SELECT nombre, puntos, nivel FROM clientes WHERE id=? AND activo=1",
        (cliente_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Cliente {cliente_id} no encontrado")
    historial = db.execute(
        "SELECT delta, tipo, concepto, fecha FROM loyalty_ledger "
        "WHERE cliente_id=? ORDER BY fecha DESC LIMIT 20",
        (cliente_id,)
    ).fetchall()
    return {
        "cliente_id": cliente_id,
        "nombre": row["nombre"],
        "saldo": float(row["puntos"] or 0),
        "nivel": row["nivel"],
        "historial": [dict(h) for h in historial],
    }
