# router/notify_router.py — REST endpoints para notificaciones POS → WA
"""
Endpoints que el POS core llama para enviar mensajes proactivos
al cliente vía WhatsApp (pedido listo, anticipo requerido, etc.).
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

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
        from messaging.sender import send_text
        await send_text(phone, text)
        return True
    except Exception as e:
        logger.error("send_text %s: %s", phone, e)
        return False


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


@router.post("/send", include_in_schema=False)
async def send_message(req: SendMessageRequest):
    from messaging.sender import send_text
    try:
        await send_text(req.phone, req.message)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
