"""Read-only base for finance query services.

Query services never mutate state: no INSERT/UPDATE/DELETE, no commit.
They feed the desktop UI and BI consumers with stable dict/DTO rows.
"""

from __future__ import annotations

from typing import Any


class FinanceQueryServiceBase:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _scalar(self, sql: str, params: tuple = (), default: str = "0") -> str:
        row = self._conn.execute(sql, params).fetchone()
        value = row[0] if row and row[0] is not None else default
        return str(value)
