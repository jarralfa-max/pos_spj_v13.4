"""Shared helpers for Meat Processing repositories.

Repositories never commit; the MeatProcessingUnitOfWork owns the transaction
boundary. Mirrors backend/infrastructure/db/repositories/inventory/base.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dt_str(value: datetime | None) -> str | None:
    """Domain entities hold real ``datetime`` objects; the schema stores TEXT
    (no sqlite3 datetime adapter is registered on Python 3.12+), so the
    repository boundary is where the conversion happens."""
    return None if value is None else value.isoformat()


def parse_dt(value: str | None) -> datetime | None:
    return None if value in (None, "") else datetime.fromisoformat(value)


def dec_str(value: Any) -> str:
    """Serialize a quantity/weight/percentage value as a plain decimal string
    (never float)."""
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        raise ValueError("No se permite float en columnas de cantidad/peso/porcentaje")
    return str(value)


def opt_dec_str(value: Any) -> str | None:
    return None if value is None else dec_str(value)


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def opt_decimal(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def bool_int(value: bool) -> int:
    return 1 if value else 0


def int_bool(value: Any) -> bool:
    return bool(value)


class MeatProcessingRepositoryBase:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _execute(self, sql: str, params: tuple = ()) -> None:
        self._conn.execute(sql, params)

    def _scalar(self, sql: str, params: tuple = (), default: Any = None) -> Any:
        row = self._conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default
