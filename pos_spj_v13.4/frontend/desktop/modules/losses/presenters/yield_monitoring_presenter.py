"""Adaptador de presentación para la página de Rendimientos (LOSS, PASS 6).

`YieldMonitoringQueryService` existía, `losses_factory.py` ya lo construía y lo
dejaba en el mapa de servicios… y ninguna página lo abría. Esto es el puente que
faltaba: convierte sus dos lecturas en filas y tarjetas, sin tocar la base.

DOS LECTURAS, UNA PANTALLA, Y NO ES CASUALIDAD
-----------------------------------------------
`recent_variances` da las desviaciones medidas y `open_alerts` las que
superaron la tolerancia. Separarlas en dos pantallas obligaría a saltar entre
ellas para responder la única pregunta que se le hace a esto: *de todo lo que se
desvió, ¿qué pasó del límite?*
"""

from __future__ import annotations

from decimal import Decimal

from frontend.desktop.components.kpi_card import KPIDTO

#: Las que el dominio marca como graves. Se nombran aquí y no se deducen del
#: texto: comparar contra una cadena suelta hace que renombrar el enum apague
#: el contador sin que nada falle.
_SEVERIDADES_GRAVES = ("CRITICAL", "HIGH")


class YieldMonitoringPresenter:
    def __init__(self, query_service, context_provider) -> None:
        self._query = query_service
        self._context_provider = context_provider

    # ── lecturas ─────────────────────────────────────────────────────────
    def variances(self, limit: int = 100):
        return self._query.recent_variances(
            branch_id=self._branch_id(), limit=limit)

    def open_alerts(self, limit: int = 100):
        return self._query.open_alerts(branch_id=self._branch_id(), limit=limit)

    # ── filas ────────────────────────────────────────────────────────────
    @staticmethod
    def variance_rows(variances) -> list[list[str]]:
        return [[
            v.production_id[:8],
            v.product_id[:8],
            f"{v.expected_output:,.3f}",
            f"{v.actual_output:,.3f}",
            f"{v.variance_quantity:+,.3f}",
            f"{v.variance_pct:+.2f}%",
            v.severity,
            (v.detected_at or "")[:16].replace("T", " "),
        ] for v in variances]

    @staticmethod
    def alert_rows(alerts) -> list[list[str]]:
        return [[
            a.severity,
            f"{a.expected_yield_pct:.2f}%",
            f"{a.actual_yield_pct:.2f}%",
            # El rango tolerado se muestra junto al real: sin él, un 92% no dice
            # si está dentro o fuera, que es justo lo que la alerta responde.
            f"{a.lower_tolerance_pct:.2f}% – {a.upper_tolerance_pct:.2f}%",
            a.message or "—",
            (a.created_at or "")[:16].replace("T", " "),
        ] for a in alerts]

    # ── tarjetas ─────────────────────────────────────────────────────────
    def kpi_cards(self, variances, alerts) -> list[KPIDTO]:
        graves = sum(1 for a in alerts if a.severity in _SEVERIDADES_GRAVES)
        return [
            KPIDTO(key="variances", title="Desviaciones", value=str(len(variances)),
                   raw_value=len(variances), variant="neutral"),
            KPIDTO(key="alerts", title="Alertas abiertas", value=str(len(alerts)),
                   raw_value=len(alerts),
                   variant="warning" if alerts else "success"),
            KPIDTO(key="critical", title="Graves", value=str(graves), raw_value=graves,
                   variant="danger" if graves else "success"),
            KPIDTO(key="worst", title="Mayor desviación",
                   value=self._worst_variance_label(variances),
                   variant="danger" if variances else "neutral"),
        ]

    @staticmethod
    def _worst_variance_label(variances) -> str:
        """La desviación más grande EN VALOR ABSOLUTO.

        Producir de más también es una desviación —sobra materia, el estándar
        está mal, o alguien registró mal— así que ordenar por el número con
        signo escondería la mitad de los casos.
        """
        if not variances:
            return "—"
        peor = max(variances, key=lambda v: abs(Decimal(v.variance_pct)))
        return f"{peor.variance_pct:+.2f}%"

    # ── contexto ─────────────────────────────────────────────────────────
    def _branch_id(self) -> str:
        return str(getattr(self._context_provider(), "active_branch_id", "") or "")
