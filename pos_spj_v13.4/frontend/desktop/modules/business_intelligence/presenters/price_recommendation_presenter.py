"""PriceRecommendationPresenter (§14/§32-40, BI-27) — feeds the "Decision
Intelligence" page: given a product+branch, estimates price elasticity from
REAL sales history (`PriceHistoryQueryService`) and produces a real
`PriceRecommendation` via `PricingIntelligenceService` (BI-16), adapted into
the unified `BusinessRecommendation` (BI-18) via `from_price_recommendation`
— the exact same adapter BI-18 already built and tested. When the pricing
decision is informational (HOLD_PRICE/REVIEW_REQUIRED — no price change
warranted), that adapter deliberately raises
`UnsupportedRecommendationSourceError` (a "hold"/"review" outcome is not
meant to enter an approval workflow, §39); this presenter catches that and
returns the raw `PriceRecommendation`'s own `reason` instead of forcing it
into a workflow it was never meant to enter.

Once a `BusinessRecommendation` is generated, BI-18's real lifecycle
transitions (`acknowledge`/`start_review`/`approve`/`reject`/`dismiss`)
apply to it — but there is still no persistence for `BusinessRecommendation`
anywhere in the repo (BI-22's own documented gap), so a transition here only
updates the page's in-memory copy; it is lost on refresh. Real persistence
is future work, not invented here.

Branch options reuse `BiDashboardQueryService.filter_options()["branches"]`
(BI-4), same real catalog BI-26's forecast page already uses, for the same
reason: the generic `BranchQueryService` scaffold has no real
SQLite-backed implementation anywhere in the repo yet.

Scoped to price recommendations only — Purchase/Production recommendations
(BI-14/15) need a real `InventoryPosition` (current_stock/incoming_stock/
supplier_lead_time_days), data this repo has no clean aggregate query for
yet; Branch recommendations (BI-17) need a per-branch product-set loop.
Building either without a real query behind it would be a fabricated
placeholder — documented in `docs/refactor/BI-27_decision_intelligence.md`,
not silently skipped.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.queries.price_history_query_service import (
    PriceHistoryQueryService,
)
from backend.application.analytics.services.bi_settings_service import BiSettingsService
from backend.application.decision_intelligence.adapters import from_price_recommendation
from backend.application.forecasting.services.pricing_intelligence_service import (
    PricingIntelligenceService,
)
from backend.application.products.queries.product_selection_query_service import (
    SearchSellableProductsQueryService,
)
from backend.domain.decision_intelligence.exceptions import (
    InvalidRecommendationTransitionError,
    UnsupportedRecommendationSourceError,
)
from backend.domain.decision_intelligence.services import recommendation_transitions as transitions
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.search_selector import SearchOption

_ACTIONS = {
    "acknowledge": transitions.acknowledge,
    "start_review": transitions.start_review,
    "approve": transitions.approve,
    "reject": transitions.reject,
    "dismiss": transitions.dismiss,
}

_STATUS_VARIANT = {
    "APPROVED": "success", "EXECUTED_EXTERNALLY": "success",
    "REJECTED": "danger", "DISMISSED": "danger", "EXPIRED": "danger",
}


class RecommendationUnavailableError(Exception):
    """Raised when a price recommendation cannot be produced (missing
    selection or not enough sale history) — the page shows this message,
    never a stack trace."""


class RecommendationTransitionError(Exception):
    """Raised when the requested lifecycle action isn't valid from the
    recommendation's current status, or the action name is unknown."""


def _product_option(dto) -> SearchOption:
    return SearchOption(id=dto.product_id, label=dto.name, subtitle=dto.code)


def map_recommendation_kpis(recommendation) -> list[KPIDTO]:
    return [
        KPIDTO(key="type", title="Tipo", value=recommendation.recommendation_type.value,
               variant="primary"),
        KPIDTO(key="priority", title="Prioridad", value=recommendation.priority.value,
               variant="warning"),
        KPIDTO(key="confidence", title="Confianza",
               value=f"{float(recommendation.confidence) * 100:.0f}%", variant="info"),
        KPIDTO(key="status", title="Estado", value=recommendation.status.value,
               variant=_STATUS_VARIANT.get(recommendation.status.value, "neutral")),
    ]


class PriceRecommendationPresenter:
    def __init__(self, connection, *, settings: BiSettingsService | None = None) -> None:
        self._products = SearchSellableProductsQueryService(connection)
        self._dashboard_query_service = BiDashboardQueryService(connection)
        self._history = PriceHistoryQueryService(connection)
        self._pricing = PricingIntelligenceService()
        self._settings = settings or BiSettingsService()

    def default_margin_review_threshold_pct(self) -> float:
        return self._settings.get("threshold_margen_bajo_pct")

    def default_valid_for_days(self) -> int:
        return self._settings.get("forecast_window_days")

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

    def generate(self, *, product_id: str, branch_id: str,
                 margin_review_threshold_pct: float, valid_for_days: int):
        """Returns (recommendation | None, price_recommendation, message | None).
        `recommendation` is None (with `message` set to the pricing reason)
        when the outcome is informational only (HOLD_PRICE/REVIEW_REQUIRED)."""
        if not product_id:
            raise RecommendationUnavailableError("Selecciona un producto.")
        if not branch_id:
            raise RecommendationUnavailableError("Selecciona una sucursal.")
        if valid_for_days <= 0:
            raise RecommendationUnavailableError("La vigencia debe ser mayor a cero días.")

        current_price = self._history.latest_price(product_id=product_id, branch_id=branch_id)
        if current_price is None:
            raise RecommendationUnavailableError(
                "No hay historial de ventas de este producto en esta sucursal.")
        current_cost = self._history.current_cost(product_id=product_id)
        history = self._history.price_quantity_history(product_id=product_id, branch_id=branch_id)
        price_quantity_history = tuple((Decimal(str(p)), Decimal(str(q))) for p, q in history)

        price_rec = self._pricing.recommend_price(
            product_id=product_id, branch_id=branch_id,
            current_price=Decimal(str(current_price)),
            current_cost=Decimal(str(current_cost)) if current_cost is not None else None,
            price_quantity_history=price_quantity_history,
            margin_review_threshold_pct=Decimal(str(margin_review_threshold_pct)),
            valid_until=date.today() + timedelta(days=valid_for_days),
        )
        try:
            recommendation = from_price_recommendation(price_rec)
            return recommendation, price_rec, None
        except UnsupportedRecommendationSourceError:
            return None, price_rec, price_rec.reason

    def apply_transition(self, recommendation, action: str):
        fn = _ACTIONS.get(action)
        if fn is None:
            raise RecommendationTransitionError(f"Acción desconocida: {action}")
        try:
            return fn(recommendation)
        except InvalidRecommendationTransitionError as exc:
            raise RecommendationTransitionError(str(exc)) from exc
