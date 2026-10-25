"""Shared helpers for finance repositories.

Repositories never commit/rollback — the Unit of Work owns the boundary.
Rows are mapped by column name regardless of the connection row_factory.
"""

from __future__ import annotations

from typing import Any


class FinanceRepositoryBase:
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

    def _execute_versioned(self, sql: str, params: tuple, entity, label: str) -> None:
        """UPDATE condicionado a la versión leída (auditoría F18). El SQL debe
        terminar en ``WHERE id=? AND row_version=?`` y fijar
        ``row_version=row_version+1``. Si otra escritura ganó, no toca nada y
        lanza ``ConcurrencyConflictError``: quien llama recarga y revalida."""
        from backend.domain.finance.exceptions import ConcurrencyConflictError

        cursor = self._conn.execute(sql, params)
        if cursor.rowcount == 0:
            raise ConcurrencyConflictError(
                f"{label} {getattr(entity, 'id', '')} cambió desde que se leyó; "
                "recargue y vuelva a intentar")
        entity.row_version = int(getattr(entity, "row_version", 0) or 0) + 1

    # ── helpers por diccionario (FIN-ERP): el nombre de columna y su valor
    # viajan juntos, así que un INSERT no puede desalinear posiciones.
    def _insert(self, table: str, values: dict) -> None:
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        self._conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                           tuple(values.values()))

    def _update(self, table: str, values: dict, *, where: str, params: tuple):
        assignments = ", ".join(f"{name}=?" for name in values)
        return self._conn.execute(f"UPDATE {table} SET {assignments} WHERE {where}",
                                  tuple(values.values()) + tuple(params))


def iso(value) -> str | None:
    """``date``/``datetime`` → texto ISO; ``None`` se queda ``None``."""
    return value.isoformat() if value is not None else None


def parse_date(value):
    from datetime import date
    return date.fromisoformat(value) if value else None
