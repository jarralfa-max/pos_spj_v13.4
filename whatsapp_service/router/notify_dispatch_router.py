# router/notify_dispatch_router.py — WA-18 (§21-22 del prompt maestro)
"""
Endpoints REST para notificaciones POS → WA vía la arquitectura nueva
(`NotificationService`/`OutboundMessageService`, WA-17/WA-18) — el
reemplazo, en paralelo, de `router/notify_router.py` (legacy, sigue
montado y sin tocar en `main.py`; ningún llamador real fue migrado
todavía a este router en esta fase).

Prefijo `/api/notify/v2` (no `/api/notify`, el del legacy) para que ambos
coexistan sin colisión de rutas mientras no se decida el corte — mismo
criterio de "paralelo, no conectado todavía" que `ApplicationFactory`
(WA-4) o `OutboundDispatcher` (WA-17) en su momento. Migrar el llamador
real (`core/integrations/whatsapp_client.py`, lado ERP) es una decisión
de cutover explícita para una fase posterior, no de esta.

Misma autenticación interna que el legacy: HMAC + identidad de servicio
vía `middleware.service_auth.require_service_auth` (WA-1).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from middleware.service_auth import require_service_auth

logger = logging.getLogger("wa.notify_v2")
router = APIRouter(
    prefix="/api/notify/v2",
    tags=["notify-v2"],
    dependencies=[Depends(require_service_auth)],
)


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


def _notification_service(request: Request):
    root = getattr(request.app.state, "composition_root", None)
    if root is None:
        raise HTTPException(status_code=503, detail="CompositionRoot no disponible todavía")
    return root.notification_service


@router.post("/pedido-listo")
async def pedido_listo(req: PedidoListoRequest, request: Request):
    service = _notification_service(request)
    try:
        message = await service.notify_order_ready(phone=req.phone, folio=req.folio, branch_name=req.sucursal)
    except Exception as exc:
        logger.error("notify_order_ready %s: %s", req.folio, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": message.status.value == "SENT", "outbox_id": message.id, "status": message.status.value}


@router.post("/anticipo")
async def anticipo_requerido(req: AnticipoRequest, request: Request):
    service = _notification_service(request)
    try:
        message = await service.notify_advance_required(phone=req.phone, folio=req.folio, amount=req.monto)
    except Exception as exc:
        logger.error("notify_advance_required %s: %s", req.folio, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": message.status.value == "SENT", "outbox_id": message.id, "status": message.status.value}


@router.post("/cotizacion")
async def cotizacion_lista(req: CotizacionRequest, request: Request):
    service = _notification_service(request)
    try:
        message = await service.notify_quote_ready(phone=req.phone, folio=req.folio, total=req.total)
    except Exception as exc:
        logger.error("notify_quote_ready %s: %s", req.folio, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": message.status.value == "SENT", "outbox_id": message.id, "status": message.status.value}


@router.post("/send")
async def send_message(req: SendMessageRequest, request: Request):
    service = _notification_service(request)
    try:
        message = await service.send_custom(phone=req.phone, message=req.message)
    except Exception as exc:
        logger.error("send_custom %s: %s", req.phone, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"ok": message.status.value == "SENT", "outbox_id": message.id, "status": message.status.value}
