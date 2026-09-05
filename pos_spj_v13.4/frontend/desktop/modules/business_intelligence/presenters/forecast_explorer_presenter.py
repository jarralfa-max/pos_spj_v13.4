"""ForecastExplorerPresenter (§14/§24-26, BI-26) — feeds the "Forecast" page:
product/branch search (canonical selection query services — §20's "usar
barra de búsqueda/autocomplete, no listas largas") and a real demand
forecast via `DemandPlanningService` (BI-12), the first real consumer of the
whole ForecastingPlatform (BI-7..11). Never composes infrastructure
persistence classes directly — that composition lives in the application
layer's own `demand_planning_factory.py` (the same wiring
`tests/integration/test_demand_planning_service_sqlite.py` already validates
end-to-end), so this presenter only imports from `backend.application.*`,
matching every other BI presenter's own layering.

Branch options reuse `BiDashboardQueryService.filter_options()["branches"]`
(BI-4) — the same real, already-live catalog that feeds the executive
dashboard's own branch filter dropdown — rather than the generic
`BranchQueryService`/`QueryDataSource` scaffold under
`backend/application/queries/`, which has no real SQLite-backed
implementation anywhere in the repo yet (it defaults to an always-empty
data source) and would make this page silently non-functional.

The default forecast horizon comes from `BiSettingsService`
("forecast_window_days", already used by the executive dashboard's own
next-week prediction) rather than a hardcoded UI literal (§23).
"""

from __future__ import annotations

from datetime import date

from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_settings_service import BiSettingsService
from backend.application.dto.charts.chart_data import ChartDataDTO, ChartSeriesDTO, ChartType
from backend.application.forecasting.services.demand_planning_factory import (
    build_demand_planning_service,
)
from backend.application.products.queries.product_selection_query_service import (
    SearchInventoryManagedProductsQueryService,
)
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.search_selector import SearchOption


class ForecastUnavailableError(Exception):
    """Raised when a forecast cannot be produced (no/insufficient sales
    history yet for the requested product+branch) — the page shows this
    message, never a stack trace."""


def _product_option(dto) -> SearchOption:
    return SearchOption(id=dto.product_id, label=dto.name, subtitle=dto.code)


def _map_run_kpis(run) -> list[KPIDTO]:
    return [
        KPIDTO(key="scope", title="Alcance", value=run.scope_value, variant="primary"),
        KPIDTO(key="horizon", title="Horizonte", value=f"{run.horizon_days} días",
               variant="info"),
        KPIDTO(key="confidence", title="Nivel de confianza",
               value=f"{float(run.confidence_level) * 100:.0f}%", variant="info"),
        KPIDTO(key="status", title="Estado del run", value=run.status.value,
               variant="success" if run.status.value == "COMPLETED" else "warning"),
    ]


def _map_forecast_chart(result) -> ChartDataDTO:
    labels = tuple(p.timestamp.isoformat() for p in result.points)
    return ChartDataDTO(
        chart_id="demand_forecast", chart_type=ChartType.LINE,
        title="Demanda pronosticada", subtitle=None, categories=labels,
        series=(
            ChartSeriesDTO(name="Pronóstico",
                            data=tuple(float(p.point_forecast) for p in result.points)),
            ChartSeriesDTO(name="Límite inferior",
                            data=tuple(float(p.lower_bound) for p in result.points)),
            ChartSeriesDTO(name="Límite superior",
                            data=tuple(float(p.upper_bound) for p in result.points)),
        ),
    )


class ForecastExplorerPresenter:
    def __init__(self, connection, *, settings: BiSettingsService | None = None) -> None:
        self._products = SearchInventoryManagedProductsQueryService(connection)
        self._dashboard_query_service = BiDashboardQueryService(connection)
        self._service = build_demand_planning_service(connection)
        self._settings = settings or BiSettingsService()

    def default_horizon_days(self) -> int:
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

    def forecast(self, *, product_id: str, branch_id: str | None,
                 horizon_days: int) -> tuple[list[KPIDTO], ChartDataDTO]:
        if not product_id:
            raise ForecastUnavailableError("Selecciona un producto para generar el forecast.")
        if horizon_days <= 0:
            raise ForecastUnavailableError("El horizonte debe ser mayor a cero días.")
        try:
            run, result = self._service.forecast_product_demand(
                product_id=product_id, branch_id=branch_id or None,
                horizon_days=horizon_days, as_of=date.today())
        except Exception as exc:  # noqa: BLE001 - not enough history, bad state, etc.
            raise ForecastUnavailableError(str(exc)) from exc
        return _map_run_kpis(run), _map_forecast_chart(result)
