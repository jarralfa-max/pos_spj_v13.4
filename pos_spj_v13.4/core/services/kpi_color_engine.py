# core/services/kpi_color_engine.py — SPJ POS v13.30 — FASE 9
"""
KPIColorEngine — Mapea estado financiero + tema → colores para KPI Cards.

REGLAS:
    - NUNCA hardcodear colores en la UI
    - La lógica de colores vive aquí, no en widgets
    - Respeta el tema activo (light / dark)
    - Prioridad de KPIs: 1.utilidad  2.flujo  3.capital

ESTADOS:
    good     → verde   (métrica saludable)
    warning  → amarillo (requiere atención)
    danger   → rojo    (acción urgente)
    neutral  → azul    (informativo)
    info     → gris    (sin umbral)

USO:
    engine = KPIColorEngine(theme='dark')
    color  = engine.color_for('margen_neto_pct', value=12.5)
    estado = engine.estado_for('margen_neto_pct', value=12.5)
    tendencia = engine.tendencia_str(current=12.5, previous=10.0)
"""
from __future__ import annotations
import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger("spj.kpi_color")

# ── Paletas por tema ──────────────────────────────────────────────────────────
# Todas las referencias de color están aquí — NUNCA en la UI.

_PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "good":    "#27AE60",   # verde
        "warning": "#F39C12",   # amarillo ámbar
        "danger":  "#E74C3C",   # rojo
        "neutral": "#2980B9",   # azul
        "info":    "#485460",   # gris oscuro
        "text":    "#FFFFFF",
        "text_sub": "rgba(255,255,255,0.80)",
    },
    "light": {
        "good":    "#1E8449",   # verde oscuro
        "warning": "#D4AC0D",   # amarillo oscuro
        "danger":  "#C0392B",   # rojo oscuro
        "neutral": "#1A5276",   # azul oscuro
        "info":    "#707B7C",   # gris
        "text":    "#FFFFFF",
        "text_sub": "rgba(255,255,255,0.85)",
    },
}

# ── Umbrales por métrica ──────────────────────────────────────────────────────
# (good_min, warning_min)  — valores por encima de good_min = good,
# entre warning_min y good_min = warning, por debajo = danger.
# None = sin umbral (neutral/info).

_THRESHOLDS: Dict[str, Tuple[Optional[float], Optional[float]]] = {
    # Prioridad 1: Utilidad
    "utilidad_neta":      (0.0, None),      # > 0 = good, < 0 = danger
    "margen_neto_pct":    (15.0, 5.0),      # >15% good, 5-15% warning, <5% danger
    "margen_bruto_pct":   (30.0, 15.0),
    "utilidad_bruta":     (0.0, None),

    # Prioridad 2: Flujo
    "ingresos":           (None, None),     # solo informativo
    "burn_rate_meses":    (6.0, 3.0),       # >6 meses good, 3-6 warning, <3 danger
    "ventas_hoy":         (None, None),
    "tickets_hoy":        (None, None),
    "ticket_promedio":    (None, None),

    # Prioridad 3: Capital
    "capital_disponible": (0.0, None),      # > 0 good, < 0 danger
    "roi_pct":            (15.0, 5.0),      # >15% good, 5-15% warning, <5% danger
    "valor_inventario":   (None, None),
    "valor_activos_fijos":(None, None),

    # Pasivos / riesgo
    "pasivo_fidelizacion":(None, None),     # solo informativo — umbral relativo al negocio
    "cxp_pendiente":      (None, None),     # solo informativo
    "egresos_total":      (None, None),     # solo informativo

    # Gastos — métrica relativa a ingresos; umbrales como % de ingresos
    # LOWER_IS_BETTER: danger si gasto excede el umbral "good"
    # Para gastos absolutos no hay umbral universal — se evalúa contra ingresos en UI.
    # Aquí solo colorizamos los ratios porcentuales de gasto:
    "pct_nomina_ingresos":    (25.0, 35.0),  # <25% good, 25-35% warning, >35% danger
    "pct_gastos_fijos":       (20.0, 30.0),  # <20% good, 20-30% warning, >30% danger
    "pct_gastos_operativos":  (15.0, 25.0),  # <15% good, 15-25% warning, >25% danger
}

# KPIs donde MENOR es mejor — lógica de color invertida
_LOWER_IS_BETTER = {
    "pasivo_fidelizacion", "cxp_pendiente", "egresos_total",
    # Ratios de gasto/ingreso (nuevos)
    "pct_nomina_ingresos", "pct_gastos_fijos", "pct_gastos_operativos",
}


class KPIColorEngine:
    """
    Determina el color y estado de cada KPI según su valor y el tema activo.
    Instanciar una vez; cambiar tema con set_theme().
    """

    def __init__(self, theme: str = "dark"):
        self._theme = theme.lower() if theme.lower() in _PALETTES else "dark"

    def set_theme(self, theme: str) -> None:
        self._theme = theme.lower() if theme.lower() in _PALETTES else "dark"

    @property
    def palette(self) -> Dict[str, str]:
        return _PALETTES[self._theme]

    # ── API principal ─────────────────────────────────────────────────────────

    def estado_for(self, metric_key: str, value: float) -> str:
        """
        Retorna: 'good' | 'warning' | 'danger' | 'neutral' | 'info'
        """
        if metric_key not in _THRESHOLDS:
            return "info"

        good_min, warn_min = _THRESHOLDS[metric_key]

        # Si no hay umbrales definidos → neutral/informativo
        if good_min is None:
            return "neutral"

        lower_better = metric_key in _LOWER_IS_BETTER

        if lower_better:
            # Lógica invertida: menor = mejor
            if warn_min is not None and value > warn_min:
                return "danger"
            if value <= good_min:
                return "good"
            return "warning"
        else:
            if value >= good_min:
                return "good"
            if warn_min is not None and value >= warn_min:
                return "warning"
            return "danger"

    def color_for(self, metric_key: str, value: float) -> str:
        """Retorna el color hex para la métrica y valor dados."""
        estado = self.estado_for(metric_key, value)
        return self.palette.get(estado, self.palette["neutral"])

    def tendencia_str(self, current: float, previous: float,
                       decimals: int = 1) -> str:
        """
        Retorna string de tendencia con signo y emoji.
        Ej: '▲ +12.5%'  '▼ -3.2%'  '→ 0.0%'
        """
        if previous == 0:
            return "→ N/D"
        pct = (current - previous) / abs(previous) * 100
        if abs(pct) < 0.1:
            return f"→ 0.0%"
        arrow = "▲" if pct > 0 else "▼"
        sign  = "+" if pct > 0 else ""
        return f"{arrow} {sign}{pct:.{decimals}f}%"

    def kpi_config(self, metric_key: str, value: float,
                    previous: float = 0) -> Dict[str, str]:
        """
        Helper completo: retorna todo lo necesario para renderizar la card.
        Returns: {color, estado, tendencia, text_color, text_sub_color}
        """
        color    = self.color_for(metric_key, value)
        estado   = self.estado_for(metric_key, value)
        tendencia = self.tendencia_str(value, previous) if previous != 0 else ""
        return {
            "color":         color,
            "estado":        estado,
            "tendencia":     tendencia,
            "text_color":    self.palette["text"],
            "text_sub_color": self.palette["text_sub"],
        }


# ── Singleton de conveniencia ─────────────────────────────────────────────────
_engine: Optional[KPIColorEngine] = None


def get_kpi_color_engine(theme: str = "dark") -> KPIColorEngine:
    """Retorna instancia global. Crea una si no existe."""
    global _engine
    if _engine is None:
        _engine = KPIColorEngine(theme)
    return _engine
