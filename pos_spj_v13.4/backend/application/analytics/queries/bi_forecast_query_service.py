"""Read-only BI query service for demand forecast.

Simple, explainable forecast: moving average over recent daily sales projected
forward. No heavy ML — deterministic and testable.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger("spj.bi.forecast")


class BiForecastQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _daily_sales(self, branch_id: str, days: int) -> list[float]:
        sql = ("SELECT DATE(fecha) d, COALESCE(SUM(total),0) t FROM ventas "
               "WHERE estado='completada' AND DATE(fecha) >= DATE('now', ?) ")
        params: list = [f"-{int(days)} days"]
        if branch_id:
            sql += "AND sucursal_id = ? "
            params.append(str(branch_id))
        sql += "GROUP BY d ORDER BY d"
        try:
            return [float(r[1] or 0) for r in self._conn.execute(sql, params).fetchall()]
        except Exception as e:
            logger.warning("_daily_sales: %s", e)
            return []

    def next_week_prediction(self, f, window_days: int = 30) -> dict:
        """Proyección de ventas de la próxima semana (media móvil * 7 días)."""
        vals = self._daily_sales(f.branch_id, days=max(1, int(window_days or 30)))
        if not vals:
            return {"value": 0.0, "avg_dia": 0.0, "muestras": 0}
        avg = sum(vals) / len(vals)
        return {"value": round(avg * 7, 2), "avg_dia": round(avg, 2),
                "muestras": len(vals)}

    def forecast_series(self, f, dias: int = 7) -> dict:
        """Serie real (últimos N días) vs pronóstico (media móvil) para graficar."""
        vals = self._daily_sales(f.branch_id, days=14)
        real_labels = []
        hoy = date.today()
        n = len(vals)
        for i in range(n):
            d = hoy - timedelta(days=(n - 1 - i))
            real_labels.append(d.strftime("%d/%m"))
        avg = (sum(vals) / len(vals)) if vals else 0.0
        fc_labels = [(hoy + timedelta(days=i + 1)).strftime("%d/%m") for i in range(dias)]
        return {
            "labels": real_labels + fc_labels,
            "real": vals + [None] * dias,
            "pronostico": [None] * n + [round(avg, 2)] * dias,
        }
