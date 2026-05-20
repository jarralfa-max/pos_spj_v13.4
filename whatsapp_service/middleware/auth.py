# middleware/auth.py — Internal API key authentication
from __future__ import annotations
from typing import Optional
from fastapi import Depends, Header, HTTPException

from config.settings import INTERNAL_API_KEY


def require_internal_key(x_internal_key: Optional[str] = Header(None)):
    """Valida la API key interna si está configurada. En dev (vacía) la omite."""
    if not INTERNAL_API_KEY:
        return
    if not x_internal_key or x_internal_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="X-Internal-Key inválida o ausente")
