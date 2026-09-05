"""Declarative, permission-aware internal navigation for Business
Intelligence (§14, BI-23). Mirrors
`frontend/desktop/modules/orders_delivery/navigation/orders_delivery_sidebar.py`
exactly.

Scoped to the sections that have a real backend behind them today (BI-4..21)
— §14's full nested tree (Ventas>Resumen/Tendencias/Productos/..., etc.) is
BI-25's job (Analytical Pages) once those sub-pages actually exist; a
top-level entry with a placeholder page is the same honest-gap pattern
`orders_delivery`/`losses` already established for their own not-yet-built
routes, not a shortcut invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from backend.application.analytics.permissions import AnalyticsPermissions as P


@dataclass(frozen=True, slots=True)
class BiNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str
    badge_key: str | None = None


BUSINESS_INTELLIGENCE_NAV: tuple[BiNavEntry, ...] = (
    BiNavEntry("bi_executive", "Resumen ejecutivo", "dashboard", P.DASHBOARD_VIEW,
               "KPIs principales, tendencias y alertas del negocio."),
    BiNavEntry("bi_sales", "Ventas", "chart", P.SALES_VIEW,
               "Ventas netas, margen y evolución por período."),
    BiNavEntry("bi_inventory", "Inventario", "inventory", P.INVENTORY_VIEW,
               "Valor, rotación, cobertura y riesgo de quiebre/sobre-stock."),
    BiNavEntry("bi_purchasing", "Compras", "purchase", P.PURCHASES_VIEW,
               "Gasto, proveedores y recomendaciones de compra."),
    BiNavEntry("bi_production", "Producción", "production", P.PRODUCTION_VIEW,
               "Demanda, rendimiento y recomendaciones de producción."),
    BiNavEntry("bi_pricing", "Precios", "price", P.PRICING_VIEW,
               "Elasticidad, margen y recomendaciones de precio."),
    BiNavEntry("bi_branches", "Sucursales", "branch", P.FORECAST_BRANCHES_VIEW,
               "Comparativo de riesgo de stock y sugerencias de transferencia."),
    BiNavEntry("bi_finance", "Finanzas", "finance", P.FINANCE_VIEW,
               "Rentabilidad, flujo de caja, cuentas por cobrar y por pagar."),
    BiNavEntry("bi_forecast", "Forecast", "forecast", P.FORECAST_VIEW,
               "Demanda, ventas, compras, producción y exactitud de modelos."),
    BiNavEntry("bi_recommendations", "Decision Intelligence", "recommendation",
               P.RECOMMENDATIONS_VIEW,
               "Recomendaciones, riesgos, oportunidades y aprobaciones.",
               badge_key="bi_recommendations_new"),
    BiNavEntry("bi_scenarios", "Escenarios", "scenario", P.SCENARIOS_VIEW,
               "Simulaciones what-if de precio, demanda y compras."),
    BiNavEntry("bi_alerts", "Alertas", "alert", P.ALERTS_VIEW,
               "Alertas activas, atendidas y suscripciones.", badge_key="bi_alerts_open"),
    BiNavEntry("bi_reports", "Reportes", "report", P.REPORTS_EXPORT,
               "Biblioteca de reportes exportables."),
)


def visible_entries(
    has_permission: Callable[[str], bool],
    badges: Mapping[str, int] | None = None,
) -> tuple[tuple[BiNavEntry, int | None], ...]:
    badges = badges or {}
    return tuple(
        (entry, badges.get(entry.badge_key) if entry.badge_key else None)
        for entry in BUSINESS_INTELLIGENCE_NAV
        if has_permission(entry.permission)
    )
