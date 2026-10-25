"""Código automático de los catálogos de Productos (PROD-23).

Categorías, marcas, atributos y sus opciones, especies, regiones anatómicas y
cortes se dan de alta con un código. Si quien captura no escribe uno, se deriva
del nombre: sin acentos, en mayúsculas, palabras unidas con ``_`` y recortado
sin partir palabras; si ya existe, se agrega ``_2``, ``_3``… Quien captura puede
reescribirlo; el código escrito a mano se respeta tal cual (en mayúsculas).

Puro: la pregunta «¿ya existe?» la responde el llamador (``is_taken``).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable

MAX_CATALOG_CODE_LENGTH = 24
_FALLBACK = "COD"


def code_from_name(name: str, *, max_length: int = MAX_CATALOG_CODE_LENGTH) -> str:
    """``"Pechuga sin hueso"`` → ``"PECHUGA_SIN_HUESO"`` (sin unicidad)."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text.upper()) if w]
    if not words:
        return _FALLBACK
    code = words[0][:max_length]
    for word in words[1:]:
        candidate = f"{code}_{word}"
        if len(candidate) > max_length:
            break
        code = candidate
    return code


def unique_code(base: str, is_taken: Callable[[str], bool], *,
                max_length: int = MAX_CATALOG_CODE_LENGTH) -> str:
    """``base`` si está libre; si no, ``base_2``, ``base_3``… dentro del largo."""
    base = (base or _FALLBACK)[:max_length]
    if not is_taken(base):
        return base
    n = 2
    while True:
        suffix = f"_{n}"
        candidate = base[:max_length - len(suffix)].rstrip("_") + suffix
        if not is_taken(candidate):
            return candidate
        n += 1


def suggest_catalog_code(name: str, is_taken: Callable[[str], bool], *,
                         max_length: int = MAX_CATALOG_CODE_LENGTH) -> str:
    return unique_code(code_from_name(name, max_length=max_length), is_taken,
                       max_length=max_length)
