# router/notify_router.py — REST endpoints para notificaciones POS → WA
"""
Endpoints que el POS core llama para enviar mensajes proactivos al cliente.
Rutas: /api/notify/pedido-listo, /api/notify/anticipo,
       /api/notify/cotizacion, /api/notify/send

Autenticación interna (WA-1): HMAC + identidad de servicio vía
`middleware.service_auth.require_service_auth` (headers X-Service-Id,
X-Timestamp, X-Nonce, X-Signature, X-Correlation-Id). Reemplaza la
comparación de string plano `X-Internal-Key` que este router reimplementaba
antes (ver whatsapp_security_audit.md S1/S2/S3). El secreto compartido sigue
siendo el mismo (`configuraciones.wa_internal_api_key`, .env como respaldo).
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from middleware.service_auth import require_service_auth

logger = logging.getLogger("wa.notify")
router = APIRouter(
    prefix="/api/notify",
    tags=["notify"],
    dependencies=[Depends(require_service_auth)],
)


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
async def pedido_listo(req: PedidoListoRequest):
    suc = f" en {req.sucursal}" if req.sucursal else ""
    ok = await _send(req.phone,
        f"✅ ¡Tu pedido *{req.folio}* está listo para recoger{suc}! 🛍️")
    return {"ok": ok}


@router.post("/anticipo")
async def anticipo_requerido(req: AnticipoRequest):
    ok = await _send(req.phone,
        f"💳 Tu pedido *{req.folio}* requiere un anticipo de *${req.monto:.2f}*.\n"
        f"Responde con el método de pago para continuar.")
    return {"ok": ok}


@router.post("/cotizacion")
async def cotizacion_lista(req: CotizacionRequest):
    ok = await _send(req.phone,
        f"📋 Tu cotización *{req.folio}* está lista.\n"
        f"Total estimado: *${req.total:.2f}*\n"
        f"Vigencia: 7 días. ¿Deseas confirmar el pedido?")
    return {"ok": ok}


@router.post("/send")
async def send_message(req: SendMessageRequest):
    from messaging.sender import send_text
    try:
        ok = await send_text(req.phone, req.message)
        return {"ok": ok}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
