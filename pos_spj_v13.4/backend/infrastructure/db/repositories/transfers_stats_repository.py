"""Read-only repository for VENTAS/transfer KPI counts shown in the UI stats bar.

Extracted from modulos/transferencias.py (Fase A): the PyQt UI ran these COUNT
queries inline. PyQt-free and headless-testable. Reads only.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class TransfersStatsRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def _count(self, where: str) -> int:
        row = self._connection.execute(
            f"SELECT COUNT(*) FROM transferencias WHERE {where}"
        ).fetchone()
        return int(row[0] or 0) if row else 0

    def get_status_counts(self) -> dict[str, int]:
        """KPI counts for the transfers stats bar."""
        return {
            "dispatched": self._count("estado='DISPATCHED'"),
            "received_this_month": self._count(
                "estado='RECEIVED' AND DATE(fecha)>=DATE('now','start of month')"
            ),
            "pending": self._count("estado='PENDING'"),
            "cancelled_this_month": self._count(
                "estado='CANCELLED' AND DATE(fecha)>=DATE('now','start of month')"
            ),
        }
