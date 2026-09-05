"""Single route registry for every internal Business Intelligence page.
Mirrors
`frontend/desktop/modules/orders_delivery/orders_delivery_routes.py` exactly.
BI-23 registers the full nav; BI-24 wired the first REAL page ("Resumen
ejecutivo"); BI-25 wires the 4 sections backed by a real
`BiDashboardService.section_data()` builder (ventas/inventario/compras/
finanzas); BI-26 wires "Forecast" to a REAL `DemandPlanningService` run
(product/branch search + generate action, not a static payload); BI-27
wires "Decision Intelligence" to a REAL `PricingIntelligenceService` run
(product+branch search + generate + real BI-18 lifecycle transitions,
session-only — no persistence exists for `BusinessRecommendation` yet).
"Producción"/"Precios"/"Sucursales" (the top-level nav sections, not the
Decision Intelligence page) have no dashboard-level aggregate query behind
them today, and Purchase/Production/Branch recommendation types (BI-14/15/
17) need real data (`InventoryPosition`, a per-branch product-set loop)
this repo has no clean aggregate query for yet — only Pricing (BI-16) is
wired. BI-28 wires "Alertas" to the REAL `AnalyticalAlertEngine` (BI-20)
evaluated against today's actual dashboard KPIs (merma/margen) — only 2 of
16 canonical alert types are wired (the rest need metric sources not
available yet). BI-29 wires "Escenarios" to the REAL `PricingWhatIfService`
(BI-19) — price what-if only; Inventory/Production/Branch what-ifs need the
same `InventoryPosition` data BI-27 already found has no clean aggregate
query for. BI-30 wires "Reportes" (a 13th nav entry — the master prompt's
§30 also names a report library/scheduling/export section not among BI-23's
original 12) to the REAL `BiExportService` — a real xlsx/pdf/csv file lands
on disk; scheduled reports are NOT built (no job-scheduling infrastructure
exists anywhere in the repo). An honest, documented gap (see
`docs/refactor/BI-25_analytical_pages.md`, `BI-26_forecast_ui.md`,
`BI-27_decision_intelligence.md`, `BI-28_alerts_ui.md`,
`BI-29_scenarios_ui.md` and `BI-30_reports.md`), not a silent one.
"""

from __future__ import annotations

from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (
    BUSINESS_INTELLIGENCE_NAV,
)

BUSINESS_INTELLIGENCE_ROUTES = {entry.page_id: entry for entry in BUSINESS_INTELLIGENCE_NAV}

# Routes with a REAL page behind them once a `connection` is supplied.
_REAL_ROUTE_BUILDERS: dict[str, str] = {
    "bi_executive": "_build_executive_dashboard",
    "bi_sales": "_build_analytical_section",
    "bi_inventory": "_build_analytical_section",
    "bi_purchasing": "_build_analytical_section",
    "bi_finance": "_build_analytical_section",
    "bi_forecast": "_build_forecast_explorer",
    "bi_recommendations": "_build_price_recommendation",
    "bi_alerts": "_build_alert_explorer",
    "bi_scenarios": "_build_pricing_scenario",
    "bi_reports": "_build_reports",
}

# BI module page_id -> BiDashboardService.section_data() section key.
_SECTION_KEY_BY_PAGE_ID: dict[str, str] = {
    "bi_sales": "ventas",
    "bi_inventory": "inventario",
    "bi_purchasing": "compras",
    "bi_finance": "finanzas",
}


def build_page(page_id: str, connection=None, *, branch_id: str | None = None,
                actor_user_id: str | None = None):
    try:
        entry = BUSINESS_INTELLIGENCE_ROUTES[page_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Business Intelligence route: {page_id}") from exc

    builder_name = _REAL_ROUTE_BUILDERS.get(page_id)
    if connection is not None and builder_name is not None:
        return globals()[builder_name](
            connection, page_id=page_id, branch_id=branch_id, actor_user_id=actor_user_id)

    from frontend.desktop.modules.business_intelligence.pages import (
        BusinessIntelligencePlaceholderPage,
    )
    return BusinessIntelligencePlaceholderPage(title=entry.title, subtitle=entry.tooltip)


def _build_executive_dashboard(connection, *, page_id: str, branch_id: str | None,
                                 actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.executive_dashboard_page import (
        ExecutiveDashboardPage,
    )
    from frontend.desktop.modules.business_intelligence.presenters.executive_dashboard_presenter import (
        ExecutiveDashboardPresenter,
    )
    return ExecutiveDashboardPage(ExecutiveDashboardPresenter(connection))


def _build_analytical_section(connection, *, page_id: str, branch_id: str | None,
                                actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.analytical_section_page import (
        AnalyticalSectionPage,
    )
    from frontend.desktop.modules.business_intelligence.presenters.analytical_section_presenter import (
        AnalyticalSectionPresenter,
    )
    entry = BUSINESS_INTELLIGENCE_ROUTES[page_id]
    section_key = _SECTION_KEY_BY_PAGE_ID[page_id]
    presenter = AnalyticalSectionPresenter(connection, section_key)
    return AnalyticalSectionPage(presenter, title=entry.title, subtitle=entry.tooltip)


def _build_forecast_explorer(connection, *, page_id: str, branch_id: str | None,
                               actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.forecast_explorer_page import (
        ForecastExplorerPage,
    )
    from frontend.desktop.modules.business_intelligence.presenters.forecast_explorer_presenter import (
        ForecastExplorerPresenter,
    )
    return ForecastExplorerPage(ForecastExplorerPresenter(connection))


def _build_price_recommendation(connection, *, page_id: str, branch_id: str | None,
                                   actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.price_recommendation_page import (
        PriceRecommendationPage,
    )
    from frontend.desktop.modules.business_intelligence.presenters.price_recommendation_presenter import (
        PriceRecommendationPresenter,
    )
    return PriceRecommendationPage(PriceRecommendationPresenter(connection))


def _build_alert_explorer(connection, *, page_id: str, branch_id: str | None,
                            actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.alert_explorer_page import (
        AlertExplorerPage,
    )
    from frontend.desktop.modules.business_intelligence.presenters.alert_explorer_presenter import (
        AlertExplorerPresenter,
    )
    return AlertExplorerPage(AlertExplorerPresenter(connection, actor_user_id=actor_user_id))


def _build_pricing_scenario(connection, *, page_id: str, branch_id: str | None,
                              actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.pricing_scenario_page import (
        PricingScenarioPage,
    )
    from frontend.desktop.modules.business_intelligence.presenters.pricing_scenario_presenter import (
        PricingScenarioPresenter,
    )
    return PricingScenarioPage(PricingScenarioPresenter(connection))


def _build_reports(connection, *, page_id: str, branch_id: str | None,
                     actor_user_id: str | None):
    from frontend.desktop.modules.business_intelligence.pages.reports_page import ReportsPage
    from frontend.desktop.modules.business_intelligence.presenters.reports_presenter import (
        ReportsPresenter,
    )
    return ReportsPage(ReportsPresenter(connection, actor_user_id=actor_user_id))
