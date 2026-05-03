
# core/forecast/seasonality_detector.py
# ── SeasonalityDetector — Patrones de Demanda Estacional ─────────────────────
#
# Detecta variación de demanda por:
#   • Día de la semana (lunes=bajo, viernes=alto, etc.)
#   • Semana del mes (primera semana suele ser mayor)
#
# Retorna un factor multiplicador por día [0..6] relativo a la media.
# Factor > 1.0 = día más activo que el promedio.
# Factor < 1.0 = día menos activo.

from __future__ import annotations
import math
from typing import Dict, List, Tuple


class SeasonalityDetector:
    """
    Calcula índices de estacionalidad semanal a partir de series de tiempo.

    Input: lista de (fecha_str, cantidad) con formato 'YYYY-MM-DD'.
    Output: dict {0..6: factor} donde 0=lunes, 6=domingo.
    """

    @staticmethod
    def weekly_factors(daily_series: List[Tuple[str, float]]) -> Dict[int, float]:
        """
        Calcula factor estacional por día de semana.

        daily_series: [(fecha_iso, cantidad), ...]

        Retorna {0: factor_lun, 1: factor_mar, ..., 6: factor_dom}
        Factor = demanda_promedio_dia / demanda_promedio_global

        Si no hay datos suficientes (< 14 días), retorna todos los factores = 1.0.
        """
        from datetime import date as _date
        from collections import defaultdict

        if len(daily_series) < 14:
            return {i: 1.0 for i in range(7)}

        totals: Dict[int, float] = defaultdict(float)
        counts: Dict[int, int]   = defaultdict(int)

        for fecha_str, qty in daily_series:
            try:
                d = _date.fromisoformat(str(fecha_str)[:10])
                dow = d.weekday()     # 0=lunes .. 6=domingo
                totals[dow] += float(qty or 0)
                counts[dow] += 1
            except (ValueError, TypeError):
                continue

        if not counts:
            return {i: 1.0 for i in range(7)}

        avg_per_day = {dow: totals[dow] / counts[dow] for dow in counts}
        global_avg  = sum(avg_per_day.values()) / len(avg_per_day)

        if global_avg <= 0:
            return {i: 1.0 for i in range(7)}

        factors = {}
        for i in range(7):
            if i in avg_per_day:
                factors[i] = round(avg_per_day[i] / global_avg, 6)
            else:
                factors[i] = 1.0

        return factors

    @staticmethod
    def apply_factor(base_forecast: float, target_date_str: str,
                     factors: Dict[int, float]) -> float:
        """Aplica el factor estacional a un pronóstico base."""
        from datetime import date as _date
        try:
            d = _date.fromisoformat(str(target_date_str)[:10])
            factor = factors.get(d.weekday(), 1.0)
            return max(0.0, round(base_forecast * factor, 6))
        except Exception:
            return base_forecast

    @staticmethod
    def describe_week_pattern(factors: Dict[int, float]) -> str:
        """Descripción legible del patrón semanal."""
        days = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        parts = [f"{days[i]}: {factors.get(i, 1.0):.2f}x" for i in range(7)]
        peak_day = max(range(7), key=lambda i: factors.get(i, 1.0))
        low_day  = min(range(7), key=lambda i: factors.get(i, 1.0))
        summary  = f"Pico: {days[peak_day]} ({factors.get(peak_day,1.0):.2f}x) | "
        summary += f"Valle: {days[low_day]} ({factors.get(low_day,1.0):.2f}x)"
        return summary + " | " + " ".join(parts)
