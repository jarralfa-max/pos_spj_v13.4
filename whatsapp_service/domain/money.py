"""Aritmética decimal del microservicio WhatsApp (PROD-22, decisión del usuario:
«todo el microservicio a Decimal», 2026-10-10).

Un solo lugar para convertir, redondear y serializar: precios, totales,
anticipos, cantidades, existencias, pesos, porcentajes y puntajes viajan como
`Decimal`.

* `to_decimal`: convierte SIEMPRE pasando por `str` (un `float` que llegue de
  una columna REAL de SQLite o de JSON no arrastra su error binario), acepta
  coma decimal del texto de WhatsApp y un valor por omisión para vacíos.
* `quantize_money`: dos decimales con redondeo comercial (HALF_UP); `round()`
  de Python redondea al par.
* `percent_of`: `base × pct / 100` en Decimal.
* `dumps_decimal`: JSON con cada `Decimal` como NÚMERO exacto (para APIs que
  exigen número: el ERP, Mercado Pago, Ollama), sin pasar por float.
* `to_json_safe`: copia con cada `Decimal` como texto (estado guardado en JSON
  que se recupera sin pérdida con `to_decimal`).
* `register_sqlite_decimal`: SQLite no sabe guardar `Decimal`; adaptador a texto
  (las columnas numéricas lo almacenan como número).
"""

from __future__ import annotations

import json
import re
import sqlite3
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
_CENTS = Decimal("0.01")


def _as_default(default) -> Decimal:
    return default if isinstance(default, Decimal) else Decimal(str(default))


def to_decimal(value, default: Decimal | str | int = ZERO) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or isinstance(value, bool):
        return _as_default(default)
    text = str(value).strip().replace(",", ".")
    if not text:
        return _as_default(default)
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return _as_default(default)


def quantize_money(value) -> Decimal:
    return to_decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def percent_of(base, pct) -> Decimal:
    return to_decimal(base) * to_decimal(pct) / HUNDRED


def clamp(value, low=ZERO, high=ONE) -> Decimal:
    return max(to_decimal(low), min(to_decimal(high), to_decimal(value)))


def money_text(value) -> str:
    """`1234.5` → `1,234.50` (para mensajes de WhatsApp)."""
    return f"{quantize_money(value):,.2f}"


_DEC_TOKEN = "__spj_decimal__:"
_DEC_PATTERN = re.compile('"' + re.escape(_DEC_TOKEN) + r'(-?[0-9.Ee+\-]+)"')


def _json_default(value):
    if isinstance(value, Decimal):
        return f"{_DEC_TOKEN}{value}"
    raise TypeError(f"{type(value).__name__} no es serializable a JSON")


def dumps_decimal(obj, **kwargs) -> str:
    kwargs.setdefault("ensure_ascii", False)
    fallback = kwargs.pop("default", None)

    def _default(value):
        if isinstance(value, Decimal) or fallback is None:
            return _json_default(value)
        return fallback(value)

    text = json.dumps(obj, default=_default, **kwargs)
    return _DEC_PATTERN.sub(lambda m: m.group(1), text)


def loads_decimal(text):
    """`json.loads` con números decimales como `Decimal` (nunca float)."""
    return json.loads(text, parse_float=Decimal)


JSON_HEADERS = {"Content-Type": "application/json"}


def to_json_safe(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    return obj


def register_sqlite_decimal() -> None:
    sqlite3.register_adapter(Decimal, str)


register_sqlite_decimal()
