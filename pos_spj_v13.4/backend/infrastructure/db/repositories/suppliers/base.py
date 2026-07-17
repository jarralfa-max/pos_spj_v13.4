"""Shared helpers for supplier repositories. Repositories never commit; UoW owns it."""

from __future__ import annotations

import unicodedata
import re
from typing import Any


class SupplierRepositoryBase:
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


def normalize_name(value: str) -> str:
    """Canonical normalized name for duplicate search + indexing."""
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)
