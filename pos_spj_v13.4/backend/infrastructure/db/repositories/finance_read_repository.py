"""Read-only repository for the finance dashboard/report queries (Fase A).

Extracted from modulos/finanzas_unificadas.py — that PyQt UI ran these SELECTs
inline. Reads only (no writes, no asientos): this module reports financial data,
it does not post journal entries, so regla 11 is not in play here. PyQt-free and
headless-testable.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class FinanceReadRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        try:
            if getattr(self._connection, "row_factory", None) is None:
                self._connection.row_factory = sqlite3.Row
        except Exception:
            pass

    def _scalar(self, sql: str, params: tuple = ()) -> Any:
        row = self._connection.execute(sql, params).fetchone()
        return row[0] if row else None

    # ── KPI / alert counts ──────────────────────────────────────────────────────
    def count_overdue_payables(self) -> int:
        return int(self._scalar(
            "SELECT COUNT(*) FROM financial_documents"
            " WHERE document_type='payable'"
            " AND status IN ('pending','partial')"
            " AND due_date < date('now')"
        ) or 0)

    def count_overdue_receivables(self) -> int:
        return int(self._scalar(
            "SELECT COUNT(*) FROM financial_documents"
            " WHERE document_type='receivable'"
            " AND status IN ('pending','partial')"
            " AND due_date < date('now')"
        ) or 0)

    def count_cash_discrepancies(self, *, days: int = 30) -> int:
        return int(self._scalar(
            "SELECT COUNT(*) FROM cierres_caja"
            " WHERE ABS(total_ventas - total_efectivo) > 0.01"
            f" AND fecha_cierre >= date('now','-{int(days)} days')"
        ) or 0)

    # ── income / expense totals ─────────────────────────────────────────────────
    def sum_sales(self) -> float:
        return float(self._scalar(
            "SELECT COALESCE(SUM(total),0) FROM ventas WHERE COALESCE(anulado,0)=0"
        ) or 0)

    def sum_purchases(self) -> float:
        return float(self._scalar("SELECT COALESCE(SUM(total),0) FROM compras") or 0)

    def expenses_by_module(self, *, limit: int = 12) -> list[tuple]:
        rows = self._connection.execute(
            "SELECT COALESCE(modulo,'Sin categoría'), SUM(monto) "
            "FROM financial_event_log "
            "GROUP BY modulo ORDER BY SUM(monto) DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [tuple(r) for r in rows]
