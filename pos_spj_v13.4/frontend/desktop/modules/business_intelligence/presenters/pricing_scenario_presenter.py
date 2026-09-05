"""PricingScenarioPresenter (§14/§41-45, BI-29) — feeds the "Escenarios"
page: given a product+branch and a hypothetical price-change %, simulates
the impact via the REAL `PricingWhatIfService` (BI-19), which reuses the
exact same price-impact formula `PricingIntelligenceService` (BI-16/BI-27)
uses for its own auto-picked recommendation — applied here to whatever
price the user wants to explore instead.

Reuses BI-27's exact plumbing for elasticity estimation
(`PriceHistoryQueryService` + `estimate_price_elasticity`) — same real
sales history, same LOW-confidence guard (raises a readable error instead
of a stack trace when there isn't enough price variation to simulate
anything honestly). Branch options reuse
`BiDashboardQueryService.filter_options()["branches"]`, same fix as
BI-26/27 for the same reason (`BranchQueryService` has no real
implementation anywhere in the repo).

Scoped to price what-if only — BI-19 also built `InventoryWhatIfService`
(demand what-ifs, reusing `ScaledTimeSeriesReader` + the real
`PurchasePlanningService`), but that needs the same `InventoryPosition`
data (current_stock/incoming_stock/supplier_lead_time_days) BI-27 already
found has no clean aggregate query in this repo yet. Same honest gap, not
fabricated here — see `docs/refactor/BI-29_scenarios_ui.md`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.queries.price_history_query_service import (
    PriceHistoryQueryService,
)
from backend.application.products.queries.product_selection_query_service import (
    SearchSellableProductsQueryService,
)
from backend.application.scenario_planning.services.pricing_what_if_service import (
    PricingWhatIfService,
)
from backend.domain.forecasting.services.price_elasticity import estimate_price_elasticity
from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.exceptions import (
    InsufficientElasticityForSimulationError,
)
from backend.domain.scenario_planning.value_objects.scenario import (
    BusinessScenario,
    ScenarioVariable,
)
from backend.shared.ids import new_uuid
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.search_selector import SearchOption


class ScenarioUnavailableError(Exception):
    """Raised when a scenario cannot be simulated (missing selection or not
    enough price/quantity history to estimate elasticity) — the page shows
    this message, never a stack trace."""


def _product_option(dto) -> SearchOption:
    return SearchOption(id=dto.product_id, label=dto.name, subtitle=dto.code)


def _pct_kpi(result, key: str, title: str) -> KPIDTO:
    value = result.delta(key)
    return KPIDTO(key=key, title=title, value=f"{float(value):+.1f}%",
                  variant="success" if value >= 0 else "danger")


def map_scenario_kpis(result) -> list[KPIDTO]:
    cards = [
        KPIDTO(key="price", title="Precio simulado",
               value=f"${float(result.scenario_metrics['price']):,.2f}", variant="primary"),
        _pct_kpi(result, "expected_volume_change_pct", "Cambio en volumen"),
        _pct_kpi(result, "expected_revenue_change_pct", "Cambio en ingresos"),
    ]
    if "expected_margin_change_pct" in result.scenario_metrics:
        cards.append(_pct_kpi(result, "expected_margin_change_pct", "Cambio en margen"))
    return cards


class PricingScenarioPresenter:
    def __init__(self, connection) -> None:
        self._products = SearchSellableProductsQueryService(connection)
        self._dashboard_query_service = BiDashboardQueryService(connection)
        self._history = PriceHistoryQueryService(connection)
        self._what_if = PricingWhatIfService()

    def search_products(self, query: str) -> list[SearchOption]:
        return [_product_option(dto) for dto in self._products.search(query=query)]

    def search_branches(self, query: str) -> list[SearchOption]:
        branches = self._dashboard_query_service.filter_options().get("branches", [])
        needle = query.strip().lower()
        return [
            SearchOption(id=b["id"], label=b["nombre"])
            for b in branches
            if not needle or needle in b["nombre"].lower()
        ]

    def simulate(self, *, product_id: str, branch_id: str, price_change_pct: float):
        if not product_id:
            raise ScenarioUnavailableError("Selecciona un producto.")
        if not branch_id:
            raise ScenarioUnavailableError("Selecciona una sucursal.")
        if price_change_pct == 0:
            raise ScenarioUnavailableError("Ingresa un cambio de precio distinto de cero.")

        current_price = self._history.latest_price(product_id=product_id, branch_id=branch_id)
        if current_price is None:
            raise ScenarioUnavailableError(
                "No hay historial de ventas de este producto en esta sucursal.")
        current_cost = self._history.current_cost(product_id=product_id)
        history = self._history.price_quantity_history(product_id=product_id, branch_id=branch_id)
        price_quantity_history = tuple((Decimal(str(p)), Decimal(str(q))) for p, q in history)
        elasticity_estimate = estimate_price_elasticity(
            product_id, branch_id, price_quantity_history)

        scenario = BusinessScenario(
            id=new_uuid(), name=f"Precio {price_change_pct:+.1f}% — {product_id}",
            variables=(ScenarioVariable(kind=ScenarioVariableKind.PRICE_CHANGE_PCT,
                                        value=Decimal(str(price_change_pct))),),
            created_at=datetime.now(timezone.utc),
        )
        try:
            return self._what_if.simulate(
                scenario=scenario, current_price=Decimal(str(current_price)),
                current_cost=Decimal(str(current_cost)) if current_cost is not None else None,
                elasticity_estimate=elasticity_estimate,
            )
        except InsufficientElasticityForSimulationError as exc:
            raise ScenarioUnavailableError(str(exc)) from exc
