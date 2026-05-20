# router/notify_router.py — REST endpoints para notificaciones POS → WA
"""
Endpoints que el POS core llama para enviar mensajes proactivos
al cliente vía WhatsApp.

Autenticación: header X-Internal-Key debe coincidir con INTERNAL_API_KEY.
Si INTERNAL_API_KEY está vacío (desarrollo), la auth se omite con advertencia.
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from messaging.sender import send_text
from middleware.auth import require_internal_key

logger = logging.getLogger("wa.notify")
router = APIRouter(prefix="/api/notify", tags=["notify"])


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


async def _send(phone: str, text: str) -> bool:
    try:
        await send_text(phone, text)
        return True
    except Exception as e:
        logger.error("send_text %s: %s", phone, e)
        return False


@router.post("/pedido-listo", dependencies=[Depends(require_internal_key)])
async def pedido_listo(req: PedidoListoRequest):
    suc = f" en {req.sucursal}" if req.sucursal else ""
    ok = await _send(req.phone,
        f"✅ ¡Tu pedido *{req.folio}* está listo para recoger{suc}! 🛍️")
    return {"ok": ok}


@router.post("/anticipo", dependencies=[Depends(require_internal_key)])
async def anticipo_requerido(req: AnticipoRequest):
    ok = await _send(req.phone,
        f"💳 Tu pedido *{req.folio}* requiere un anticipo de *${req.monto:.2f}*.\n"
        f"Responde con el método de pago para continuar.")
    return {"ok": ok}


@router.post("/cotizacion", dependencies=[Depends(require_internal_key)])
async def cotizacion_lista(req: CotizacionRequest):
    ok = await _send(req.phone,
        f"📋 Tu cotización *{req.folio}* está lista.\n"
        f"Total estimado: *${req.total:.2f}*\n"
        f"Vigencia: 7 días. ¿Deseas confirmar el pedido?")
    return {"ok": ok}


@router.post("/send", include_in_schema=False,
             dependencies=[Depends(require_internal_key)])
async def send_message(req: SendMessageRequest):
    ok = await _send(req.phone, req.message)
    if not ok:
        raise HTTPException(status_code=500, detail="Error al enviar mensaje")
    return {"ok": True}
