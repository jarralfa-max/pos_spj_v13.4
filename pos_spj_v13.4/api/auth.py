# api/auth.py — Autenticación para el gateway REST del ERP
"""
Soporta dos mecanismos:
  1. API Key en header X-API-Key  (para integraciones máquina-a-máquina)
  2. Bearer token JWT             (para clientes web/móvil — futuro)

La API Key se configura en la tabla `configuraciones` con clave
`api_gateway_key`, o via variable de entorno ERP_API_KEY.
"""
from __future__ import annotations
import os
import secrets
import logging
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger("spj.api.auth")

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_configured_key(db=None) -> str | None:
    """Obtiene la API key activa: ENV > BD. Retorna ``None`` si no hay
    ninguna configurada — CRM-40 (Fase 6): sin fallback a un valor por
    defecto conocido/adivinable. Un valor por defecto público (aunque
    documentado como "solo para desarrollo") es, en la práctica, una
    puerta trasera si alguien olvida configurar la clave real en
    producción — el mismo razonamiento que ya llevó a eliminar el
    fallback de SHA-256/texto plano en autenticación (CRM-28)."""
    env_key = os.environ.get("ERP_API_KEY", "")
    if env_key:
        return env_key
    if db:
        try:
            row = db.execute(
                "SELECT valor FROM configuraciones WHERE clave='api_gateway_key'"
            ).fetchone()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
    return None


def verify_api_key(api_key: str = Security(_API_KEY_HEADER), db=None) -> str:
    """
    Dependency que valida la API Key. Lanza 401 si es inválida o falta,
    503 si el servidor no tiene ninguna clave configurada (fail-closed:
    nunca acepta una clave por defecto conocida). Usa comparación en
    tiempo constante para evitar timing attacks.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key requerida en header X-API-Key",
        )
    configured = _get_configured_key(db)
    if not configured:
        logger.error(
            "API Key no configurada (ERP_API_KEY o configuraciones.api_gateway_key) "
            "— rechazando todas las solicitudes hasta que se configure"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API Key no configurada en el servidor",
        )
    if not secrets.compare_digest(api_key, configured):
        logger.warning("API Key inválida recibida")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida",
        )
    return api_key
