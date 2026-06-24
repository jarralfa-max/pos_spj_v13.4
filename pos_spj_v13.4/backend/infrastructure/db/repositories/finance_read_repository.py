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

    # ── table/list reads (positional tuples; UI builds its dicts) ───────────────
    def _rows(self, sql: str) -> list[tuple]:
        return [tuple(r) for r in self._connection.execute(sql).fetchall()]

    def list_cash_closures(self, *, limit: int = 100) -> list[tuple]:
        return self._rows(
            "SELECT fecha_cierre, sucursal_id, usuario, turno, "
            "total_ventas, total_efectivo "
            f"FROM cierres_caja ORDER BY fecha_cierre DESC LIMIT {int(limit)}"
        )

    def list_capital_movements(self, *, limit: int = 100) -> list[tuple]:
        return self._rows(
            "SELECT created_at, movement_type, partner_name, concept, "
            "payment_method, amount, reference, status "
            f"FROM capital_movements ORDER BY created_at DESC LIMIT {int(limit)}"
        )

    def list_treasury_capital(self, *, limit: int = 100) -> list[tuple]:
        return self._rows(
            "SELECT fecha, tipo, usuario, descripcion, '', monto, '', 'confirmado' "
            f"FROM treasury_capital ORDER BY fecha DESC LIMIT {int(limit)}"
        )

    def list_treasury_ledger(self, *, limit: int = 200) -> list[tuple]:
        return self._rows(
            "SELECT fecha, tipo, categoria, concepto, referencia, "
            "ingreso, egreso, usuario "
            f"FROM treasury_ledger ORDER BY fecha DESC LIMIT {int(limit)}"
        )

    def list_journal_entries(self, *, limit: int = 200) -> list[tuple]:
        return self._rows(
            "SELECT created_at, event_type, source_module, "
            "debit_account, credit_account, amount, source_folio, user "
            f"FROM journal_entries ORDER BY created_at DESC LIMIT {int(limit)}"
        )

    def list_financial_event_log(self, *, limit: int = 200) -> list[tuple]:
        return self._rows(
            "SELECT timestamp, evento, modulo, cuenta_debe, cuenta_haber, "
            "monto, referencia_id, usuario_id "
            f"FROM financial_event_log ORDER BY timestamp DESC LIMIT {int(limit)}"
        )

    def list_active_suppliers(self, *, limit: int = 300) -> list[tuple]:
        return self._rows(
            "SELECT id,nombre,telefono,email,contacto,"
            "COALESCE(condiciones_pago,0) FROM proveedores "
            f"WHERE COALESCE(activo,1)=1 ORDER BY nombre LIMIT {int(limit)}"
        )

    def list_customer_credit(self, *, limit: int = 300) -> list[tuple]:
        return self._rows(
            "SELECT nombre, "
            " COALESCE(limite_credito, credit_limit, 0) AS limite, "
            " COALESCE(saldo, 0) AS saldo_usado, "
            " COALESCE(ultima_compra, '') AS ultima_compra "
            "FROM clientes "
            "WHERE COALESCE(activo,1)=1 "
            f"ORDER BY nombre LIMIT {int(limit)}"
        )

    def get_recent_activity(self, *, limit: int = 20) -> list[dict]:
        """Recent financial activity feed: journal_entries (if present) UNION
        ventas + compras + cierres_caja, newest first."""
        parts = []
        try:
            self._connection.execute("SELECT 1 FROM journal_entries LIMIT 1")
            parts.append(
                "SELECT created_at AS fecha, event_type AS tipo, 'Finanzas' AS modulo,"
                " COALESCE(source_folio,'') AS concepto, amount AS monto, user AS usuario"
                " FROM journal_entries"
            )
        except Exception:
            pass
        parts.append(
            "SELECT fecha, 'Venta' AS tipo, 'Ventas' AS modulo,"
            " COALESCE(folio,'V-'||id) AS concepto, total AS monto,"
            " COALESCE(usuario,'') AS usuario FROM ventas WHERE estado != 'cancelada'"
        )
        parts.append(
            "SELECT fecha, 'Compra' AS tipo, 'Compras' AS modulo,"
            " COALESCE(folio,'C-'||id) AS concepto, total AS monto,"
            " COALESCE(usuario,'') AS usuario FROM compras"
        )
        parts.append(
            "SELECT fecha_cierre AS fecha, 'Cierre caja' AS tipo, 'Caja' AS modulo,"
            " COALESCE(turno,'Cierre-'||id) AS concepto, total_ventas AS monto,"
            " COALESCE(usuario,'') AS usuario FROM cierres_caja"
        )
        union_sql = " UNION ALL ".join(parts)
        cur = self._connection.execute(
            f"SELECT * FROM ({union_sql}) ORDER BY fecha DESC LIMIT {int(limit)}"
        )
        return [
            {"fecha": r[0], "tipo": r[1], "modulo": r[2],
             "concepto": r[3], "monto": r[4], "usuario": r[5]}
            for r in cur.fetchall()
        ]
