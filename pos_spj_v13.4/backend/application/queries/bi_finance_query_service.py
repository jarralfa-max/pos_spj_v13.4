"""Read-only BI query service for finance metrics: CxC, CxP, expenses, purchases.

Reads the canonical accounts_receivable / accounts_payable / gastos / compras
tables. All identity columns are UUIDv7 TEXT (never int-cast).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.finance")


class BiFinanceQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _scalar(self, sql, params=()) -> float:
        try:
            row = self._conn.execute(sql, params).fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        except Exception as e:
            logger.warning("BiFinanceQueryService: %s", e)
            return 0.0

    def accounts_receivable_total(self, f) -> float:
        """CxC: saldo pendiente de clientes (balance > 0)."""
        sql = "SELECT COALESCE(SUM(balance),0) FROM accounts_receivable WHERE balance > 0"
        params: list = []
        if f.branch_id:
            sql += " AND sucursal_id = ?"
            params.append(str(f.branch_id))
        return self._scalar(sql, params)

    def accounts_payable_total(self, f) -> float:
        """CxP: saldo pendiente a proveedores (balance > 0)."""
        sql = "SELECT COALESCE(SUM(balance),0) FROM accounts_payable WHERE balance > 0"
        params: list = []
        if f.branch_id:
            sql += " AND sucursal_id = ?"
            params.append(str(f.branch_id))
        return self._scalar(sql, params)

    def expenses(self, f) -> float:
        """Gastos operativos del periodo (tabla gastos, alcance global)."""
        return self._scalar(
            "SELECT COALESCE(SUM(monto),0) FROM gastos "
            "WHERE DATE(fecha) BETWEEN ? AND ?", [f.date_from, f.date_to])

    def purchases_total(self, f) -> float:
        """Compras del periodo (para comparativo compra vs venta)."""
        sql = ("SELECT COALESCE(SUM(total),0) FROM compras "
               "WHERE estado != 'cancelada' AND DATE(fecha) BETWEEN ? AND ?")
        params: list = [f.date_from, f.date_to]
        if f.branch_id:
            sql += " AND sucursal_id = ?"
            params.append(str(f.branch_id))
        return self._scalar(sql, params)

    def top_suppliers(self, f, limit: int = 10) -> list[dict]:
        try:
            rows = self._conn.execute(
                "SELECT COALESCE(pr.nombre,'—') n, COALESCE(SUM(c.total),0) t "
                "FROM compras c LEFT JOIN proveedores pr ON pr.id=c.proveedor_id "
                "WHERE c.estado != 'cancelada' AND DATE(c.fecha) BETWEEN ? AND ? "
                "GROUP BY c.proveedor_id ORDER BY t DESC LIMIT ?",
                [f.date_from, f.date_to, limit]).fetchall()
            return [{"nombre": r[0], "total": float(r[1] or 0)} for r in rows]
        except Exception as e:
            logger.warning("top_suppliers: %s", e)
            return []
