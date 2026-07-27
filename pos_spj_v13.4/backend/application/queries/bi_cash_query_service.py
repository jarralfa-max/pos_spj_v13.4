"""Read-only BI query service for cash register (caja) metrics.

Reads movimientos_caja (direct cash movements) and cierres_caja (Z cuts). Only
explicit cash movements count — purchases are NOT reflected in caja unless a cash
movement was registered for them.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.cash")

# Clasificación robusta de tipo de movimiento de caja.
_INGRESO = "LOWER(tipo) IN ('ingreso','entrada','deposito','venta','abono')"
_EGRESO = "LOWER(tipo) IN ('egreso','salida','retiro','gasto')"


class BiCashQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _q(self, sql, params=()):
        try:
            return self._conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.warning("BiCashQueryService: %s", e)
            return []

    def _branch(self, f, alias="") -> tuple[str, list]:
        col = f"{alias}sucursal_id" if alias else "sucursal_id"
        if f.branch_id:
            return f" AND {col} = ?", [str(f.branch_id)]
        return "", []

    def cash_totals(self, f) -> dict:
        """Ingresos y egresos directos de caja + número de cortes del periodo."""
        wb, pb = self._branch(f)
        row = self._q(
            f"SELECT COALESCE(SUM(CASE WHEN {_INGRESO} THEN monto ELSE 0 END),0), "
            f"COALESCE(SUM(CASE WHEN {_EGRESO} THEN monto ELSE 0 END),0) "
            "FROM movimientos_caja WHERE DATE(fecha) BETWEEN ? AND ?" + wb,
            [f.date_from, f.date_to] + pb)
        ingresos = float(row[0][0]) if row else 0.0
        egresos = float(row[0][1]) if row else 0.0
        cortes = self._q(
            "SELECT COUNT(*) FROM cierres_caja "
            "WHERE DATE(COALESCE(fecha_cierre, fecha_apertura)) BETWEEN ? AND ?" + wb,
            [f.date_from, f.date_to] + pb)
        num_cortes = int(cortes[0][0]) if cortes else 0
        return {"ingresos": ingresos, "egresos": egresos,
                "saldo": ingresos - egresos, "num_cortes": num_cortes}

    def daily_behavior(self, f) -> list[tuple[str, float, float]]:
        """(día, ingresos, egresos) para graficar el comportamiento diario."""
        wb, pb = self._branch(f)
        rows = self._q(
            f"SELECT DATE(fecha) d, "
            f"COALESCE(SUM(CASE WHEN {_INGRESO} THEN monto ELSE 0 END),0), "
            f"COALESCE(SUM(CASE WHEN {_EGRESO} THEN monto ELSE 0 END),0) "
            "FROM movimientos_caja WHERE DATE(fecha) BETWEEN ? AND ?" + wb +
            " GROUP BY d ORDER BY d", [f.date_from, f.date_to] + pb)
        return [(str(r[0])[5:], float(r[1] or 0), float(r[2] or 0)) for r in rows]

    def recent_cortes(self, f, limit: int = 15) -> list[dict]:
        wb, pb = self._branch(f)
        rows = self._q(
            "SELECT COALESCE(fecha_cierre, fecha_apertura) fc, total_ventas, "
            "total_efectivo, COALESCE(diferencia,0) "
            "FROM cierres_caja WHERE DATE(COALESCE(fecha_cierre, fecha_apertura)) "
            "BETWEEN ? AND ?" + wb + " ORDER BY fc DESC LIMIT ?",
            [f.date_from, f.date_to] + pb + [limit])
        return [{"fecha": str(r[0] or "")[:16], "total_ventas": float(r[1] or 0),
                 "efectivo": float(r[2] or 0), "diferencia": float(r[3] or 0)}
                for r in rows]
