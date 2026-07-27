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

# Clave por defecto solo para desarrollo local — en producción debe
# configurarse via ERP_API_KEY o tabla configuraciones.
_DEFAULT_DEV_KEY = "dev-only-change-in-production"


def _get_configured_key(db=None) -> str:
    """Obtiene la API key activa: ENV > BD > default dev."""
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
    return _DEFAULT_DEV_KEY


def verify_api_key(api_key: str = Security(_API_KEY_HEADER), db=None) -> str:
    """
    Dependency que valida la API Key. Lanza 401 si es inválida.
    Usa comparación en tiempo constante para evitar timing attacks.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key requerida en header X-API-Key",
        )
    configured = _get_configured_key(db)
    if not secrets.compare_digest(api_key, configured):
        logger.warning("API Key inválida recibida")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida",
        )
    return api_key
