# middleware/auth.py — Internal API key authentication
from __future__ import annotations
from typing import Optional
from fastapi import Header, HTTPException


def require_internal_key(x_internal_key: Optional[str] = Header(None)):
    """Valida la API key interna.

    La clave se resuelve desde config.settings.get_internal_api_key(), que debe
    preferir la configuración guardada desde el módulo WhatsApp y usar .env solo
    como respaldo técnico.
    """
    from config.settings import get_internal_api_key

    internal_key = get_internal_api_key()
    if not internal_key:
        return
    if not x_internal_key or x_internal_key != internal_key:
        raise HTTPException(status_code=401, detail="X-Internal-Key inválida o ausente")
