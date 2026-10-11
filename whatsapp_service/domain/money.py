"""Aritmética decimal del microservicio WhatsApp (PROD-22, decisión del usuario:
«todo el microservicio a Decimal», 2026-10-10).

Un solo lugar para convertir y redondear: precios, totales, anticipos,
cantidades, existencias, pesos, porcentajes y puntajes viajan como `Decimal`.

* `to_decimal`: convierte SIEMPRE pasando por `str` (un `float` que llegue de
  una columna REAL de SQLite o de JSON no arrastra su error binario), acepta
  coma decimal del texto de WhatsApp y un valor por omisión para vacíos.
* `quantize_money`: dos decimales con redondeo comercial (HALF_UP); `round()`
  de Python redondea al par.
* `percent_of`: `base × pct / 100` en Decimal.
* `register_sqlite_decimal`: SQLite no sabe guardar `Decimal`; se registra un
  adaptador a texto (las columnas numéricas lo almacenan como número).
"""

from __future__ import annotations

import sqlite3
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
_CENTS = Decimal("0.01")


def to_decimal(value, default: Decimal | str | int = ZERO) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or isinstance(value, bool):
        return Decimal(default) if not isinstance(default, Decimal) else default
    text = str(value).strip().replace(",", ".")
    if not text:
        return Decimal(default) if not isinstance(default, Decimal) else default
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal(default) if not isinstance(default, Decimal) else default


def quantize_money(value) -> Decimal:
    return to_decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def percent_of(base, pct) -> Decimal:
    return to_decimal(base) * to_decimal(pct) / HUNDRED


def clamp(value, low=ZERO, high=ONE) -> Decimal:
    v = to_decimal(value)
    return max(to_decimal(low), min(to_decimal(high), v))


def money_text(value) -> str:
    """`1234.5` → `1,234.50` (para mensajes de WhatsApp)."""
    return f"{quantize_money(value):,.2f}"


def register_sqlite_decimal() -> None:
    sqlite3.register_adapter(Decimal, str)


register_sqlite_decimal()
