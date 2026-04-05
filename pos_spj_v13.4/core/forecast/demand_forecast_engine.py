
# core/forecast/demand_forecast_engine.py
# ── DemandForecastEngine — Motor de Pronóstico de Demanda ─────────────────────
#
# ALGORITMOS:
#   1. moving_avg_7   — Media móvil 7 días
#   2. moving_avg_30  — Media móvil 30 días
#   3. weighted_avg   — Promedio ponderado (pesos lineales, más reciente = más peso)
#   4. exp_smoothing  — Suavizado exponencial simple (alpha configurable)
#
# FLUJO POR PRODUCTO:
#   1. Cargar serie de ventas diarias (ventas + detalles_venta)
#   2. Detectar estacionalidad semanal
#   3. Calcular pronóstico con método seleccionado
#   4. Ajustar por factor estacional
#   5. Guardar en demand_forecast
#   6. Calcular métricas de precisión (MAE, RMSE, MAPE)
#
# PROTECCIÓN:
#   • Si historial < min_history_days → saltar producto (no calcular)
#   • Nunca forecast negativo

from __future__ import annotations

import logging
import math
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.forecast.seasonality_detector import SeasonalityDetector
from core.forecast.safety_stock_calculator import SafetyStockCalculator

logger = logging.getLogger("spj.forecast.demand")

MIN_HISTORY_DAYS_DEFAULT = 14


class DemandForecastEngine:
    """
    Motor de pronóstico de demanda para un producto+sucursal.

    Uso:
        engine = DemandForecastEngine(db)
        results = engine.forecast_product(product_id=1, branch_id=1)
    """

    def __init__(self, db):
        self.db = db

    # ── Config ─────────────────────────────────────────────────────────────────

    def _get_config(self, key: str, default: str) -> str:
        try:
            row = self.db.fetchone(
                "SELECT valor FROM configuraciones WHERE clave=?", (key,)
            )
            return row["valor"] if row else default
        except Exception:
            return default

    def _get_product_config(self, product_id: int, branch_id: int) -> dict:
        try:
            row = self.db.fetchone("""
                SELECT lead_time_days, service_level_pct, alpha, method_preferred, min_history_days
                FROM product_forecast_config
                WHERE product_id=? AND branch_id=? AND activo=1
            """, (product_id, branch_id))
            if row:
                return dict(row)
        except Exception:
            pass
        return {
            "lead_time_days":    int(self._get_config("forecast_lead_time_days", "2")),
            "service_level_pct": float(self._get_config("forecast_service_level", "95")),
            "alpha":             float(self._get_config("forecast_alpha", "0.3")),
            "method_preferred":  self._get_config("forecast_method", "weighted_avg"),
            "min_history_days":  int(self._get_config("forecast_min_history", "14")),
        }

    # ── Datos históricos ───────────────────────────────────────────────────────

    def _get_daily_sales(
        self, product_id: int, branch_id: int, days: int = 90
    ) -> List[Tuple[str, float]]:
        """
        Retorna [(fecha_iso, qty_vendida)] por día de los últimos N días.
        Combina ventas con detalles_venta.
        """
        since = (date.today() - timedelta(days=days)).isoformat()
        try:
            rows = self.db.fetchall("""
                SELECT
                    date(v.fecha) AS dia,
                    SUM(CAST(dv.cantidad AS REAL)) AS qty
                FROM detalles_venta dv
                JOIN ventas v ON v.id = dv.venta_id
                WHERE dv.producto_id = ?
                  AND (v.sucursal_id = ? OR ? = 0)
                  AND v.estado NOT IN ('cancelada','anulada')
                  AND v.fecha >= ?
                GROUP BY date(v.fecha)
                ORDER BY dia ASC
            """, (product_id, branch_id, branch_id, since))
            return [(r["dia"], float(r["qty"] or 0)) for r in rows]
        except Exception as exc:
            logger.warning("get_daily_sales prod=%d suc=%d: %s", product_id, branch_id, exc)
            return []

    def _fill_zeros(
        self, series: List[Tuple[str, float]], days: int
    ) -> List[float]:
        """
        Rellena días sin ventas con 0 y retorna solo los valores numéricos.
        """
        by_date: Dict[str, float] = {d: q for d, q in series}
        today = date.today()
        result = []
        for i in range(days, 0, -1):
            d = (today - timedelta(days=i)).isoformat()
            result.append(by_date.get(d, 0.0))
        return result

    # ── Algoritmos ─────────────────────────────────────────────────────────────

    @staticmethod
    def moving_avg(values: List[float], window: int) -> float:
        """Media móvil simple de los últimos `window` valores."""
        if not values: return 0.0
        subset = values[-window:] if len(values) >= window else values
        return sum(subset) / len(subset)

    @staticmethod
    def weighted_avg(values: List[float], window: int = 14) -> float:
        """
        Promedio ponderado: peso lineal creciente (más reciente = más peso).
        weights = [1, 2, 3, ..., n]
        """
        if not values: return 0.0
        subset = values[-window:] if len(values) >= window else values
        n = len(subset)
        weights = list(range(1, n + 1))
        total_w = sum(weights)
        if total_w <= 0: return 0.0
        return sum(v * w for v, w in zip(subset, weights)) / total_w

    @staticmethod
    def exp_smoothing(values: List[float], alpha: float = 0.3) -> float:
        """
        Suavizado exponencial simple.
        F_t = alpha × D_{t-1} + (1-alpha) × F_{t-1}
        Retorna el pronóstico del siguiente período.
        """
        if not values: return 0.0
        alpha = max(0.01, min(0.99, alpha))
        forecast = values[0]
        for v in values[1:]:
            forecast = alpha * v + (1 - alpha) * forecast
        return forecast

    def _choose_best_method(
        self, product_id: int, branch_id: int, default: str
    ) -> str:
        """Elige el método con menor MAE histórico, o el default."""
        try:
            row = self.db.fetchone("""
                SELECT method FROM forecast_metrics
                WHERE product_id=? AND branch_id=?
                ORDER BY mae ASC LIMIT 1
            """, (product_id, branch_id))
            if row and row["method"]:
                return row["method"]
        except Exception:
            pass
        return default

    # ── Pronóstico ─────────────────────────────────────────────────────────────

    def forecast_product(
        self,
        product_id: int,
        branch_id: int,
        horizon_days: int = 7,
        run_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Calcula pronóstico para un producto+sucursal.

        Retorna dict con:
            product_id, branch_id, method, avg_daily,
            forecast_total, forecast_by_day, seasonality_factors,
            safety_stock, reorder_point, confidence
        O None si no hay historial suficiente.
        """
        cfg = self._get_product_config(product_id, branch_id)
        min_hist = cfg["min_history_days"]
        alpha    = cfg["alpha"]
        method   = self._choose_best_method(
            product_id, branch_id, cfg["method_preferred"]
        )

        series = self._get_daily_sales(product_id, branch_id, days=90)
        if len(series) < min_hist:
            logger.debug(
                "SKIP prod=%d suc=%d — solo %d días de historial (mínimo %d)",
                product_id, branch_id, len(series), min_hist
            )
            return None

        # Serie diaria completa (con ceros)
        daily_values = self._fill_zeros(series, days=min(90, len(series) + 30))

        # Factor estacional
        factors = SeasonalityDetector.weekly_factors(series)

        # Pronóstico base por día según método
        base_map = {
            "moving_avg_7":  lambda: self.moving_avg(daily_values, 7),
            "moving_avg_30": lambda: self.moving_avg(daily_values, 30),
            "weighted_avg":  lambda: self.weighted_avg(daily_values, 14),
            "exp_smoothing": lambda: self.exp_smoothing(daily_values, alpha),
        }
        calc = base_map.get(method, base_map["weighted_avg"])
        base_daily = max(0.0, calc())
        avg_daily  = max(0.0, self.moving_avg(daily_values, 30))

        # Forecast ajustado por estacionalidad para cada día del horizonte
        today = date.today()
        forecast_by_day = []
        total_forecast  = 0.0
        for i in range(1, horizon_days + 1):
            target = today + timedelta(days=i)
            adj = SeasonalityDetector.apply_factor(
                base_daily, target.isoformat(), factors
            )
            adj = max(0.0, adj)
            forecast_by_day.append((target.isoformat(), round(adj, 4)))
            total_forecast += adj

        # Desviación estándar para stock seguridad
        lead_time  = cfg["lead_time_days"]
        svc_level  = cfg["service_level_pct"]
        ss = SafetyStockCalculator.safety_stock(daily_values, lead_time, svc_level)
        rop = SafetyStockCalculator.reorder_point(avg_daily, lead_time, ss)

        # Confianza: basada en coeficiente de variación (CV)
        std = SafetyStockCalculator.std_dev(daily_values)
        cv  = std / avg_daily if avg_daily > 0 else 1.0
        confidence = round(max(0.1, min(1.0, 1 / (1 + cv))), 4)

        return {
            "product_id":          product_id,
            "branch_id":           branch_id,
            "method":              method,
            "avg_daily_demand":    round(avg_daily, 6),
            "base_daily":          round(base_daily, 6),
            "forecast_total":      round(total_forecast, 4),
            "forecast_by_day":     forecast_by_day,
            "seasonality_factors": factors,
            "safety_stock":        round(ss, 4),
            "reorder_point":       round(rop, 4),
            "confidence":          confidence,
            "lead_time_days":      lead_time,
            "horizon_days":        horizon_days,
            "run_id":              run_id,
        }

    # ── Persistir forecast ──────────────────────────────────────────────────────

    def save_forecast(self, result: dict) -> int:
        """Guarda forecast diario en demand_forecast. Retorna número de filas."""
        if not result or not result.get("forecast_by_day"):
            return 0

        pid     = result["product_id"]
        bid     = result["branch_id"]
        method  = result["method"]
        conf    = result["confidence"]
        hor     = result["horizon_days"]
        run_id  = result.get("run_id", "")
        factors = result["seasonality_factors"]

        # Eliminar forecasts previos del mismo horizonte para no acumular
        try:
            today = date.today().isoformat()
            self.db.execute("""
                DELETE FROM demand_forecast
                WHERE product_id=? AND branch_id=? AND forecast_date >= ?
                  AND run_id != ?
            """, (pid, bid, today, run_id or "NONE"))
        except Exception:
            pass

        n = 0
        for (fdate, fqty) in result["forecast_by_day"]:
            fid    = str(uuid.uuid4())
            dow    = 0
            try:
                dow = date.fromisoformat(fdate).weekday()
            except Exception:
                pass
            sf = factors.get(dow, 1.0)

            self.db.execute("""
                INSERT INTO demand_forecast
                    (id, product_id, branch_id, forecast_date,
                     predicted_demand, confidence, method,
                     horizon_days, lower_bound, upper_bound,
                     seasonality_factor, run_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (fid, pid, bid, fdate, fqty, conf, method,
                  hor,
                  max(0.0, fqty * 0.8),   # lower bound −20%
                  fqty * 1.2,              # upper bound +20%
                  sf, run_id or ""))
            n += 1
        return n

    # ── Métricas de precisión ──────────────────────────────────────────────────

    def evaluate_accuracy(
        self, product_id: int, branch_id: int, days: int = 30
    ) -> Optional[dict]:
        """
        Evalúa precisión del forecast comparando predicciones pasadas vs ventas reales.
        Retorna MAE, RMSE, MAPE.
        """
        since = (date.today() - timedelta(days=days)).isoformat()
        try:
            rows = self.db.fetchall("""
                SELECT df.forecast_date, df.predicted_demand, df.method,
                       COALESCE(SUM(CAST(dv.cantidad AS REAL)), 0) AS real_demand
                FROM demand_forecast df
                LEFT JOIN detalles_venta dv
                    ON dv.producto_id = df.product_id
                    AND date(
                        (SELECT v.fecha FROM ventas v WHERE v.id = dv.venta_id)
                    ) = df.forecast_date
                WHERE df.product_id=? AND df.branch_id=? AND df.forecast_date >= ?
                  AND df.forecast_date < date('now')
                GROUP BY df.forecast_date, df.method
                ORDER BY df.forecast_date
            """, (product_id, branch_id, since))
        except Exception as exc:
            logger.warning("evaluate_accuracy: %s", exc)
            return None

        if not rows or len(rows) < 3:
            return None

        errors, sq_errors, pct_errors = [], [], []
        method = rows[0]["method"]
        for r in rows:
            pred  = float(r["predicted_demand"] or 0)
            real  = float(r["real_demand"] or 0)
            err   = abs(pred - real)
            errors.append(err)
            sq_errors.append(err ** 2)
            if real > 0:
                pct_errors.append(err / real * 100)

        n    = len(errors)
        mae  = sum(errors)    / n
        rmse = math.sqrt(sum(sq_errors) / n)
        mape = sum(pct_errors) / len(pct_errors) if pct_errors else 0.0
        bias = sum(
            float(r["predicted_demand"] or 0) - float(r["real_demand"] or 0)
            for r in rows
        ) / n

        # Guardar métricas
        try:
            mid = str(uuid.uuid4())
            self.db.execute("""
                INSERT INTO forecast_metrics
                    (id, product_id, branch_id, method, mae, rmse, mape, bias,
                     n_evaluations, last_evaluated)
                VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(product_id, branch_id, method) DO UPDATE SET
                    mae=excluded.mae, rmse=excluded.rmse,
                    mape=excluded.mape, bias=excluded.bias,
                    n_evaluations=excluded.n_evaluations,
                    last_evaluated=excluded.last_evaluated
            """, (mid, product_id, branch_id, method,
                  round(mae, 6), round(rmse, 6),
                  round(mape, 4), round(bias, 6), n))
        except Exception as exc:
            logger.warning("save_metrics: %s", exc)

        return {
            "product_id": product_id, "branch_id": branch_id,
            "method": method, "mae": round(mae, 4),
            "rmse": round(rmse, 4), "mape": round(mape, 2),
            "bias": round(bias, 4), "n": n,
        }
