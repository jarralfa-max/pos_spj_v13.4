"""Helpers compartidos por los repositorios de Seguridad.

Los repositorios nunca hacen commit; el UnitOfWork es el dueño de la
transacción. Réplica de
`backend/infrastructure/db/repositories/settings/base.py`.
"""

from __future__ import annotations

from typing import Any


class SecurityRepositoryBase:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self._conn.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _table_exists(self, name: str) -> bool:
        return bool(self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
            (name,),
        ).fetchone())
