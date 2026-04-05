# webhook/whatsapp.py — Webhook oficial de WhatsApp Cloud API
"""
GET  /webhook → Verificación de Meta
POST /webhook → Recepción de mensajes
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Request, Query, Response

from models.message import IncomingMessage
from middleware.rate_limiter import RateLimiter

logger = logging.getLogger("wa.webhook")
router = APIRouter()

# Estas se inyectan desde main.py al arrancar
_message_router = None
_number_router = None
_conversation_store = None
_rate_limiter = RateLimiter()


def init_webhook(message_router, number_router, conversation_store):
    global _message_router, _number_router, _conversation_store
    _message_router = message_router
    _number_router = number_router
    _conversation_store = conversation_store


@router.get("/webhook")
async def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge"),
):
    """Verificación del webhook por Meta."""
    from config.settings import WA_VERIFY_TOKEN
    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        logger.info("Webhook verificado exitosamente")
        return Response(content=challenge, media_type="text/plain")
    logger.warning("Verificación fallida: token=%s", token)
    return Response(status_code=403)


@router.post("/webhook")
async def receive_message(request: Request):
    """Recibe mensajes entrantes de WhatsApp."""
    try:
        data = await request.json()
    except Exception:
        return {"status": "error", "detail": "invalid json"}

    # Ignorar status updates (read receipts, etc.)
    if RateLimiter.is_status_update(data):
        return {"status": "ok"}

    # Ignorar mensajes de grupos
    if RateLimiter.is_group_message(data):
        return {"status": "ok"}

    # Parsear mensaje
    msg = IncomingMessage.from_webhook(data)
    if not msg:
        return {"status": "ok"}

    # Idempotencia: no procesar duplicados
    if _conversation_store and _conversation_store.is_duplicate(msg.message_id):
        logger.debug("Duplicado ignorado: %s", msg.message_id)
        return {"status": "ok"}

    # Rate limiting
    if not _rate_limiter.is_allowed(msg.from_number):
        logger.warning("Rate limited: %s", msg.from_number)
        return {"status": "ok"}

    # Registrar mensaje
    if _conversation_store:
        _conversation_store.log_message(
            msg.message_id, msg.from_number, "in",
            msg.text or msg.interactive_id or msg.type.value)

    # Routing por número
    numero_cfg = _number_router.route(msg) if _number_router else None

    # Procesar mensaje
    if _message_router and numero_cfg:
        try:
            await _message_router.route(msg, numero_cfg)
        except Exception as e:
            logger.error("Error procesando mensaje de %s: %s",
                         msg.from_number, e, exc_info=True)

    return {"status": "ok"}
