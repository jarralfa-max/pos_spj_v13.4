# api/routers/clientes.py — Endpoints de clientes
from __future__ import annotations
import logging
from dataclasses import asdict
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db
from api.auth import verify_api_key
from repositories.cliente_repository import ClienteRepository

router = APIRouter(prefix="/clientes", tags=["clientes"])
logger = logging.getLogger("spj.api.clientes")

# CRM-25: identity fields the desktop/WhatsApp callers of this router
# already rely on — kept as an explicit projection (not `SELECT *` via the
# repo) so the response shape doesn't silently widen when routed through
# `ClienteRepository`, which returns every column.
_CLIENTE_SEARCH_FIELDS = ("id", "nombre", "telefono", "email", "puntos", "nivel")
_CLIENTE_DETAIL_FIELDS = (
    "id", "nombre", "telefono", "email", "direccion", "rfc",
    "puntos", "nivel", "activo", "fecha_registro",
)


def _bridge_customer_to_crm(db, legacy_customer_id: str) -> None:
    """Eagerly create/resolve this customer's Customer Master bridge row
    (CRM-25), same as `ModuloVentas._bridge_customer_to_crm` — never blocks
    the API response."""
    try:
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            ResolveLegacyCustomerUseCase,
        )
        ResolveLegacyCustomerUseCase().execute(db, legacy_customer_id=str(legacy_customer_id))
    except Exception as _crm_e:
        logger.debug("CRM legacy customer bridge (eager, API): %s", _crm_e)

# CRM-21: pseudo-actor for CRM-13's permission-gated query services when
# called from a system integration (no human user session) — mirrors the
# 'WHATSAPP_BOT' literal already used as `usuario` elsewhere in
# integrations/pos_adapter.py for the same "system caller" concept.
_WHATSAPP_BOT_ACTOR = "WHATSAPP_BOT"


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
    repo = ClienteRepository(db)
    rows = repo.buscar(q, limit=min(limit, 100)) if q else repo.get_all(limit=min(limit, 100))
    return {"clientes": [{k: r.get(k) for k in _CLIENTE_SEARCH_FIELDS} for r in rows]}


@router.get("/{cliente_id}")
async def get_cliente(
    cliente_id: str,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Retorna datos completos de un cliente."""
    row = ClienteRepository(db).get_by_id(cliente_id)
    if not row:
        raise HTTPException(404, f"Cliente {cliente_id} no encontrado")
    cliente = {k: row.get(k) for k in _CLIENTE_DETAIL_FIELDS}

    # Últimas ventas y saldo de puntos: propiedad de Ventas/Fidelidad, no de
    # Clientes — mismo tipo de lectura cross-context de solo lectura que
    # CustomerHistoryQueryService ya hace, se mantiene como SQL directo aquí.
    ventas = db.execute(
        "SELECT id, folio, total, fecha, estado FROM ventas "
        "WHERE cliente_id=? ORDER BY fecha DESC LIMIT 10",
        (cliente_id,)
    ).fetchall()

    puntos_row = db.execute(
        "SELECT COALESCE(SUM(delta), 0) AS saldo "
        "FROM loyalty_ledger WHERE cliente_id=? AND tipo='credito'",
        (cliente_id,)
    ).fetchone()

    return {
        "cliente": cliente,
        "ultimas_ventas": [dict(v) for v in ventas],
        "saldo_puntos": float(puntos_row["saldo"]) if puntos_row else float(row.get("puntos") or 0),
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
        codigo_qr = str(_uuid.uuid4())[:12]
        cliente_id = ClienteRepository(db).crear(
            nombre=body.nombre, telefono=body.telefono, email=body.email,
            direccion=body.direccion, codigo_fidelidad=codigo_qr,
        )
        # ClienteRepository.crear() doesn't set rfc/nivel — the table's own
        # `nivel` default ('normal') differs from what this endpoint always
        # set explicitly ('Bronce'), so preserve that behavior here.
        db.execute("UPDATE clientes SET rfc=?, nivel='Bronce' WHERE id=?", (body.rfc, cliente_id))
        db.commit()
        _bridge_customer_to_crm(db, cliente_id)
        return {"ok": True, "cliente_id": cliente_id, "nombre": body.nombre}
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/{cliente_id}/crm-summary")
async def get_crm_summary(
    cliente_id: str,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """CRM-21: enriches a WhatsApp reply with the Customer Master's view of
    this (legacy) customer — loyalty tier/points and order history, plus a
    friendlier CRM `customer_number`/`display_name` if a bridge row exists.

    `LoyaltyCustomerSummaryQuery`/`CustomerOrdersSummaryQuery` accept the
    LEGACY `cliente_id` directly (their SQL filters legacy tables by it —
    see their own docstrings), so no identity bridging is needed for those
    two. Only the friendlier name/folio needs
    `ResolveLegacyCustomerUseCase`. Degrades to `"available": false` per
    section (never a 500) if the Customer Master's permission checker isn't
    wired for this deployment yet (`CustomerAuthorizationPolicy()` fails
    closed with no checker configured — a separate, pre-existing gap, not
    something this endpoint can fix)."""
    row = db.execute("SELECT id FROM clientes WHERE id=?", (cliente_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Cliente {cliente_id} no encontrado")

    from backend.application.customers.queries.customer_orders_summary_query import (
        CustomerOrdersSummaryQuery,
    )
    from backend.application.customers.queries.loyalty_customer_summary_query import (
        LoyaltyCustomerSummaryQuery,
    )
    from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
        ResolveLegacyCustomerUseCase,
    )

    result: dict = {"cliente_id": cliente_id, "loyalty": None, "orders": None,
                    "customer_number": None, "display_name": None}
    try:
        loyalty = LoyaltyCustomerSummaryQuery(db).get_summary(
            cliente_id, actor_user_id=_WHATSAPP_BOT_ACTOR)
        result["loyalty"] = asdict(loyalty)
    except Exception as e:
        logger.debug("crm-summary loyalty unavailable: %s", e)
    try:
        orders = CustomerOrdersSummaryQuery(db).get_summary(
            cliente_id, actor_user_id=_WHATSAPP_BOT_ACTOR)
        result["orders"] = asdict(orders)
    except Exception as e:
        logger.debug("crm-summary orders unavailable: %s", e)
    try:
        new_customer_id = ResolveLegacyCustomerUseCase().execute(
            db, legacy_customer_id=cliente_id)
        bridged = db.execute(
            "SELECT customer_number, display_name FROM customers WHERE id=?",
            (new_customer_id,)).fetchone()
        if bridged:
            result["customer_number"] = bridged["customer_number"]
            result["display_name"] = bridged["display_name"]
    except Exception as e:
        logger.debug("crm-summary bridge unavailable: %s", e)
    return result


@router.get("/{cliente_id}/puntos")
async def get_puntos(
    cliente_id: str,
    _key: str = Depends(verify_api_key),
    db=Depends(get_db),
):
    """Retorna historial y saldo de puntos de fidelidad."""
    row = ClienteRepository(db).get_by_id(cliente_id)
    if not row or not row.get("activo", 1):
        raise HTTPException(404, f"Cliente {cliente_id} no encontrado")
    historial = db.execute(
        "SELECT delta, tipo, concepto, fecha FROM loyalty_ledger "
        "WHERE cliente_id=? ORDER BY fecha DESC LIMIT 20",
        (cliente_id,)
    ).fetchall()
    return {
        "cliente_id": cliente_id,
        "nombre": row["nombre"],
        "saldo": float(row.get("puntos") or 0),
        "nivel": row.get("nivel"),
        "historial": [dict(h) for h in historial],
    }
