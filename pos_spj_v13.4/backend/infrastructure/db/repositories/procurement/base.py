"""Shared helpers for procurement repositories. Repositories never commit; the
ProcurementUnitOfWork owns the transaction boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dec_str(value: Any) -> str:
    """Serialize a money/quantity value as a plain decimal string (never float)."""
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        raise ValueError("No se permite float en columnas monetarias/cantidad")
    return str(value)


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


class ProcurementRepositoryBase:
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
