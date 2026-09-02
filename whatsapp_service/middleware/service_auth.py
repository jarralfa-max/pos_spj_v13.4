# middleware/service_auth.py — HMAC service-to-service auth (WA-1)
"""
Autenticación interna ERP↔microservicio vía HMAC + identidad de servicio.

Reemplaza la comparación de string plano de `X-Internal-Key` que antes
reimplementaba cada router (`notify_router.py:_check_internal_key`,
`delivery_router.py:_check_internal_key`) — ambas con `!=` (no constant-time)
y fail-open si la clave no estaba configurada (whatsapp_security_audit.md,
S1/S2/S3). El secreto compartido sigue siendo el mismo
(`configuraciones.wa_internal_api_key` / `WA_INTERNAL_API_KEY` env, resuelto
vía `config.settings.get_internal_api_key()`) — lo que cambia es cómo se usa:
como clave HMAC en vez de valor comparado directamente.

Formato de la firma — debe coincidir byte a byte con la copia del lado ERP en
`pos_spj_v13.4/core/integrations/whatsapp_client.py` (ese archivo está en un
paquete top-level distinto, así que mantiene su propia copia corta de esta
misma lógica en vez de importar este módulo):

    body_hash      = sha256(body).hexdigest()
    signed_string  = f"{service_id}:{timestamp}:{nonce}:{body_hash}"
    signature      = HMAC-SHA256(signed_string, secret).hexdigest()

Headers esperados en cada request protegida:
    X-Service-Id      — identidad del servicio llamante (ver constantes abajo)
    X-Timestamp        — segundos Unix, como string (str(int(time.time())))
    X-Nonce             — valor aleatorio único por request
    X-Signature         — hex digest HMAC-SHA256 sobre signed_string
    X-Correlation-Id    — id de trazabilidad; NO participa en la firma
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Dict, Optional

from fastapi import Header, HTTPException, Request

logger = logging.getLogger("wa.service_auth")

# ── Identidades de servicio ───────────────────────────────────────────────────
WHATSAPP_CHANNEL_SERVICE = "whatsapp-channel"  # este microservicio
ERP_CORE_SERVICE = "erp-core"                   # el ERP desktop, llamando

# Tolerancia de reloj para el timestamp (segundos) — también se usa como
# ventana de retención del cache de nonces vistos.
_TIMESTAMP_TOLERANCE_SECONDS = 120

# Cache de nonces vistos: nonce -> expiry (epoch seconds). Este servicio
# corre en un solo proceso hoy (ver main.py); un despliegue multi-worker
# necesitaría un store compartido (Redis, etc.) — fuera de alcance de esta
# fase.
_seen_nonces: Dict[str, float] = {}


def sign_request(service_id: str, timestamp: str, nonce: str, body: bytes, secret: str) -> str:
    """HMAC-SHA256 hex digest sobre `service_id:timestamp:nonce:sha256(body)`.

    Se hashea el body una sola vez (SHA-256) y se incluye su hex digest en la
    cadena firmada, en vez de HMACear el body completo directamente — evita
    procesar bodies grandes dos veces. Ver docstring del módulo para el
    formato exacto; debe mantenerse compatible con la copia del lado ERP.
    """
    body_hash = hashlib.sha256(body or b"").hexdigest()
    signed_string = f"{service_id}:{timestamp}:{nonce}:{body_hash}"
    return hmac.new(secret.encode("utf-8"), signed_string.encode("utf-8"), hashlib.sha256).hexdigest()


def _prune_expired_nonces(now: float) -> None:
    expired = [n for n, exp in _seen_nonces.items() if exp <= now]
    for n in expired:
        _seen_nonces.pop(n, None)


def _is_replayed_nonce(nonce: str, now: float) -> bool:
    """True si el nonce ya fue visto dentro de la ventana de tolerancia."""
    _prune_expired_nonces(now)
    if nonce in _seen_nonces:
        return True
    _seen_nonces[nonce] = now + _TIMESTAMP_TOLERANCE_SECONDS
    return False


def reset_nonce_cache() -> None:
    """Limpia el cache de nonces vistos. Uso principal: tests."""
    _seen_nonces.clear()


async def require_service_auth(
    request: Request,
    x_service_id: Optional[str] = Header(None),
    x_timestamp: Optional[str] = Header(None),
    x_nonce: Optional[str] = Header(None),
    x_signature: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None),
) -> None:
    """Dependencia FastAPI: valida autenticación de servicio a servicio.

    No retorna nada — su único efecto es lanzar HTTPException si la request
    no está correctamente autenticada (patrón ya usado en este código para
    dependencias de solo validación).
    """
    from config.settings import get_internal_api_key, is_production

    secret = get_internal_api_key()
    if not secret:
        if is_production():
            logger.error(
                "WA_INTERNAL_API_KEY no configurada en producción; "
                "rechazando request al canal interno ERP↔microservicio "
                "(whatsapp_security_audit.md S1/S8)."
            )
            raise HTTPException(status_code=503, detail="Service auth not configured")
        logger.warning(
            "WA_INTERNAL_API_KEY no configurada — endpoint interno sin "
            "autenticación (permitido solo fuera de producción)."
        )
        return

    if not (x_service_id and x_timestamp and x_nonce and x_signature):
        logger.warning("require_service_auth: headers de autenticación de servicio faltantes")
        raise HTTPException(status_code=401, detail="Missing service auth headers")

    try:
        ts = int(x_timestamp)
    except (TypeError, ValueError):
        logger.warning("require_service_auth: X-Timestamp inválido: %r", x_timestamp)
        raise HTTPException(status_code=401, detail="Invalid timestamp")

    now = time.time()
    if abs(now - ts) > _TIMESTAMP_TOLERANCE_SECONDS:
        logger.warning(
            "require_service_auth: timestamp fuera de tolerancia (recibido=%s, servidor=%s)",
            ts, now,
        )
        raise HTTPException(status_code=401, detail="Timestamp out of tolerance")

    if _is_replayed_nonce(x_nonce, now):
        logger.warning("require_service_auth: nonce reutilizado (posible replay): %s", x_nonce)
        raise HTTPException(status_code=401, detail="Replayed nonce")

    body = await request.body()
    expected = sign_request(x_service_id, x_timestamp, x_nonce, body, secret)
    if not hmac.compare_digest(expected, x_signature):
        logger.warning(
            "require_service_auth: firma inválida (service_id=%s, correlation_id=%s)",
            x_service_id, x_correlation_id,
        )
        raise HTTPException(status_code=401, detail="Invalid signature")
