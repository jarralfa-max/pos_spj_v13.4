
# core/forecast/safety_stock_calculator.py
# ── SafetyStockCalculator — Cálculos de Inventario de Seguridad ───────────────
#
# Fórmulas:
#   safety_stock  = Z × σ_demanda × √(lead_time)
#   reorder_point = (demanda_promedio × lead_time) + safety_stock
#   qty_a_pedir   = forecast_periodo + safety_stock − stock_actual
#
# Z según nivel de servicio:
#   90% → 1.28   95% → 1.65   98% → 2.05   99% → 2.33

from __future__ import annotations
import math
from typing import List

# Z-scores para niveles de servicio comunes
_Z_TABLE = {
    90.0: 1.28,
    91.0: 1.34,
    92.0: 1.41,
    93.0: 1.48,
    94.0: 1.56,
    95.0: 1.65,
    96.0: 1.75,
    97.0: 1.88,
    98.0: 2.05,
    99.0: 2.33,
    99.5: 2.58,
    99.9: 3.09,
}

# Umbrales de urgencia
_CRITICAL_DAYS  = 2    # < 2 días cobertura → crítico
_LOW_DAYS       = 5    # < 5 días cobertura → bajo


def _z_score(service_level_pct: float) -> float:
    """Obtiene Z más cercano para el nivel de servicio dado."""
    if service_level_pct >= 99.9: return 3.09
    if service_level_pct <= 90.0: return 1.28
    best = min(_Z_TABLE.keys(), key=lambda k: abs(k - service_level_pct))
    return _Z_TABLE[best]


class SafetyStockCalculator:

    @staticmethod
    def std_dev(daily_demand: List[float]) -> float:
        """Desviación estándar de la demanda diaria."""
        n = len(daily_demand)
        if n < 2:
            return 0.0
        mean = sum(daily_demand) / n
        variance = sum((x - mean) ** 2 for x in daily_demand) / (n - 1)
        return math.sqrt(variance)

    @staticmethod
    def safety_stock(
        daily_demand: List[float],
        lead_time_days: int,
        service_level_pct: float = 95.0,
    ) -> float:
        """
        safety_stock = Z × σ_demanda × √(lead_time)

        daily_demand: lista de demandas diarias históricas
        lead_time_days: tiempo de entrega del proveedor en días
        service_level_pct: 95 → Z=1.65
        """
        if not daily_demand or lead_time_days <= 0:
            return 0.0
        z = _z_score(service_level_pct)
        sigma = SafetyStockCalculator.std_dev(daily_demand)
        ss = z * sigma * math.sqrt(max(1, lead_time_days))
        return round(max(0.0, ss), 4)

    @staticmethod
    def reorder_point(
        avg_daily_demand: float,
        lead_time_days: int,
        safety_stock: float,
    ) -> float:
        """
        reorder_point = (demanda_promedio × lead_time) + safety_stock
        """
        rop = avg_daily_demand * max(1, lead_time_days) + safety_stock
        return round(max(0.0, rop), 4)

    @staticmethod
    def recommended_quantity(
        forecast_period: float,
        safety_stock: float,
        current_stock: float,
        min_order: float = 0.0,
    ) -> float:
        """
        qty = forecast_periodo + safety_stock - stock_actual

        Nunca retorna negativo. Aplica mínimo de pedido si configurado.
        """
        qty = forecast_period + safety_stock - current_stock
        qty = max(0.0, qty)
        if qty > 0 and min_order > 0:
            qty = max(qty, min_order)
        return round(qty, 4)

    @staticmethod
    def days_coverage(current_stock: float, avg_daily_demand: float) -> float:
        """Días de cobertura con el stock actual."""
        if avg_daily_demand <= 0:
            return 9999.0
        return round(current_stock / avg_daily_demand, 2)

    @staticmethod
    def urgency_level(days_cov: float) -> str:
        if days_cov <= _CRITICAL_DAYS:  return "critico"
        if days_cov <= _LOW_DAYS:       return "bajo"
        if days_cov <= 14:              return "normal"
        return "ok"
