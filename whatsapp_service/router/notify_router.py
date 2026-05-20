# router/notify_router.py — REST endpoints para notificaciones POS → WA
"""
Endpoints que el POS core llama para enviar mensajes proactivos al cliente.
Rutas: /api/notify/pedido-listo, /api/notify/anticipo,
       /api/notify/cotizacion, /api/notify/send

Autenticación interna: header X-Internal-Key debe coincidir con WA_INTERNAL_API_KEY.
Si WA_INTERNAL_API_KEY está vacío se registra un warning pero no se bloquea
(modo dev sin configurar — cambiar en producción).
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("wa.notify")
router = APIRouter(prefix="/api/notify", tags=["notify"])


# ── Auth guard ────────────────────────────────────────────────────────────────

def _check_internal_key(x_internal_key: Optional[str]) -> None:
    """Valida la API key interna. Lanza 403 si es inválida."""
    from config.settings import WA_INTERNAL_API_KEY
    if not WA_INTERNAL_API_KEY:
        logger.warning(
            "WA_INTERNAL_API_KEY not configured — notify endpoints are unprotected. "
            "Set WA_INTERNAL_API_KEY in .env for production."
        )
        return  # Dev mode: allow through with warning
    if not x_internal_key or x_internal_key != WA_INTERNAL_API_KEY:
        logger.warning("notify_router: unauthorized request — bad X-Internal-Key")
        raise HTTPException(status_code=403, detail="Unauthorized")


# ── Request models ────────────────────────────────────────────────────────────

class PedidoListoRequest(BaseModel):
    phone: str
    folio: str
    sucursal: str = ""


class AnticipoRequest(BaseModel):
    phone: str
    folio: str
    monto: float


class CotizacionRequest(BaseModel):
    phone: str
    folio: str
    total: float


class SendMessageRequest(BaseModel):
    phone: str
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send(phone: str, text: str) -> bool:
    try:
        from messaging.sender import send_text
        return await send_text(phone, text)
    except Exception as e:
        logger.error("send_text %s: %s", phone, e)
        return False


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/pedido-listo")
async def pedido_listo(req: PedidoListoRequest,
                       x_internal_key: Optional[str] = Header(None)):
    _check_internal_key(x_internal_key)
    suc = f" en {req.sucursal}" if req.sucursal else ""
    ok = await _send(req.phone,
        f"✅ ¡Tu pedido *{req.folio}* está listo para recoger{suc}! 🛍️")
    return {"ok": ok}


@router.post("/anticipo")
async def anticipo_requerido(req: AnticipoRequest,
                             x_internal_key: Optional[str] = Header(None)):
    _check_internal_key(x_internal_key)
    ok = await _send(req.phone,
        f"💳 Tu pedido *{req.folio}* requiere un anticipo de *${req.monto:.2f}*.\n"
        f"Responde con el método de pago para continuar.")
    return {"ok": ok}


@router.post("/cotizacion")
async def cotizacion_lista(req: CotizacionRequest,
                           x_internal_key: Optional[str] = Header(None)):
    _check_internal_key(x_internal_key)
    ok = await _send(req.phone,
        f"📋 Tu cotización *{req.folio}* está lista.\n"
        f"Total estimado: *${req.total:.2f}*\n"
        f"Vigencia: 7 días. ¿Deseas confirmar el pedido?")
    return {"ok": ok}


@router.post("/send")
async def send_message(req: SendMessageRequest,
                       x_internal_key: Optional[str] = Header(None)):
    _check_internal_key(x_internal_key)
    from messaging.sender import send_text
    try:
        ok = await send_text(req.phone, req.message)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
