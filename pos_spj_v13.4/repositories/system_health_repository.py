# repositories/system_health_repository.py
"""Read-only repository for system health/diagnostics metrics.

Owns the SQL that the health monitor UI helper used to run inline. Every read is
defensive: diagnostics must never raise (a missing/legacy column degrades to a
safe default), matching the historical behavior of the monitor.
"""
from __future__ import annotations

import logging

from core.db.connection import get_connection

logger = logging.getLogger("spj.health.repo")


class SystemHealthRepository:
    def __init__(self, connection_factory=None):
        # Factory (not a held connection) to mirror the monitor's per-call pooling.
        self._factory = connection_factory or get_connection

    def _conn(self):
        return self._factory()

    def ping(self) -> bool:
        """True si la conexión responde a un SELECT trivial."""
        try:
            self._conn().execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def error_count_24h(self) -> int:
        """Número de eventos ERROR/CRITICAL en las últimas 24h (0 si no aplica)."""
        try:
            row = self._conn().execute(
                "SELECT COUNT(*) FROM logs "
                "WHERE nivel IN ('ERROR','CRITICAL') "
                "AND fecha >= datetime('now','-1 day')"
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def pending_sync_count(self) -> int:
        """Eventos de sync pendientes de enviar (0 si la tabla no aplica)."""
        try:
            row = self._conn().execute(
                "SELECT COUNT(*) FROM sync_eventos WHERE enviado=0"
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def recent_errors(self, limit: int = 50) -> list:
        """Últimos errores/avisos del log (lista vacía si no aplica)."""
        try:
            rows = self._conn().execute(
                "SELECT nivel, modulo, mensaje, fecha "
                "FROM logs WHERE nivel IN ('ERROR','CRITICAL','WARNING') "
                "ORDER BY fecha DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
