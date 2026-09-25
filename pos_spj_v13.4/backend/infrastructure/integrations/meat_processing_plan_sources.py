"""De dónde salen las líneas sugeridas del Plan de producción (decisión del
usuario, 2026-09-25): la reposición de Inventario y el pronóstico de BI.

Ninguna fuente decide por el planeador: proponen producto y cantidad; el
planeador elige el proceso y el producto objetivo al aceptar la sugerencia.
Sólo se proponen productos PRODUCIBLES (dato de Productos).

- Reposición: las sugerencias ABIERTAS que Inventario ya calculó
  (mínimos/máximos) para la sucursal.
- Pronóstico: el `ProductionPlanningService` de BI (pronóstico de demanda sobre
  ventas reales + posición de inventario), el mismo motor de Inteligencia, no
  un cálculo propio.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from backend.application.meat_processing.ports import PlanSuggestion

logger = logging.getLogger("spj.meat_processing.plan_sources")


def _producibles(conn, branch_id: str) -> dict[str, str]:
    """{producto: nombre} de lo producible habilitado en la sucursal."""
    from backend.application.products.queries.product_selection_query_service import (
        ProductCatalogSearchQueryService,
        ProductSearchQuery,
    )
    return {dto.product_id: dto.name for dto in ProductCatalogSearchQueryService(conn).search(
        ProductSearchQuery(producible_only=True, branch_id=branch_id, page_size=500))}


def _detalle_pronostico(recomendacion) -> str:
    demanda = Decimal(str(recomendacion.expected_demand)).quantize(Decimal("0.01"))
    prioridad = getattr(recomendacion.priority, "value", recomendacion.priority)
    return f"Demanda esperada {demanda} · prioridad {prioridad}"


class ReplenishmentPlanSource:
    label = "Reposición de Inventario"

    def __init__(self, connection) -> None:
        self._conn = connection
        self.note: str | None = None

    def suggestions(self, branch_id: str) -> list[PlanSuggestion]:
        from backend.application.inventory.queries.replenishment_suggestion_query_service import (
            ReplenishmentSuggestionQueryService,
        )
        producibles = _producibles(self._conn, branch_id)
        # Inventario deja abiertas las de cada generación; para planear cuenta
        # la MÁS RECIENTE de cada producto (llegan de la más nueva a la más vieja).
        recientes: dict[str, object] = {}
        for s in ReplenishmentSuggestionQueryService(self._conn).open_for_branch(branch_id):
            recientes.setdefault(s.product_id, s)
        abiertas = list(recientes.values())
        salida = [PlanSuggestion(
            product_id=s.product_id, product_name=producibles[s.product_id],
            quantity=s.suggested_quantity, source_type="REPLENISHMENT",
            source_reference_id=s.suggestion_id,
            detail=f"Disponible {s.current_available.normalize():f} · urgencia {s.urgency}")
            for s in abiertas if s.product_id in producibles and s.suggested_quantity > 0]
        if not salida:
            self.note = ("Inventario no tiene sugerencias de reposición abiertas para "
                         "productos producibles de esta sucursal.")
        return salida


class ForecastPlanSource:
    label = "Pronóstico de BI"

    HORIZON_DAYS = 7
    COVERAGE_DAYS = Decimal("7")
    OVERSTOCK_DAYS = Decimal("30")
    CONFIDENCE = Decimal("0.90")

    def __init__(self, connection, *, today: date | None = None) -> None:
        self._conn = connection
        self._today = today or date.today()
        self.note: str | None = None

    def _planning_service(self):
        from backend.application.forecasting.services.default_series_catalog import (
            DAILY_SALES_BY_PRODUCT_KEY,
            build_default_series_catalog,
        )
        from backend.application.forecasting.services.demand_planning_service import (
            DemandPlanningService,
        )
        from backend.application.forecasting.services.inventory_forecast_service import (
            InventoryForecastService,
        )
        from backend.application.forecasting.services.production_planning_service import (
            ProductionPlanningService,
        )
        from backend.application.forecasting.services.time_series_dataset_builder import (
            TimeSeriesDatasetBuilder,
        )
        from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_model_repository import (  # noqa: E501
            SqliteForecastModelRepository,
        )
        from backend.infrastructure.db.repositories.forecasting.sqlite_forecast_run_repository import (  # noqa: E501
            SqliteForecastRunRepository,
        )
        from backend.infrastructure.db.repositories.forecasting.sqlite_time_series_reader import (
            SqliteDailyProductSalesReader,
        )
        serie = build_default_series_catalog().get(DAILY_SALES_BY_PRODUCT_KEY)
        datos = TimeSeriesDatasetBuilder(SqliteDailyProductSalesReader(self._conn))
        demanda = DemandPlanningService(datos, SqliteForecastModelRepository(self._conn),
                                        SqliteForecastRunRepository(self._conn), serie)
        return ProductionPlanningService(InventoryForecastService(demanda, datos, serie),
                                         datos, serie)

    def suggestions(self, branch_id: str) -> list[PlanSuggestion]:
        from backend.application.inventory.queries.availability_query_service import (
            InventoryAvailabilityQueryService,
        )
        from backend.domain.forecasting.value_objects.inventory_forecast import (
            InventoryPosition,
        )
        producibles = _producibles(self._conn, branch_id)
        if not producibles:
            self.note = "No hay productos producibles habilitados en esta sucursal."
            return []
        try:
            motor = self._planning_service()
        except Exception as exc:  # noqa: BLE001 — BI no instalado: se dice, no se inventa
            logger.exception("pronóstico de BI no disponible")
            self.note = f"El pronóstico de BI no está disponible: {exc}"
            return []
        disponibilidad = InventoryAvailabilityQueryService(self._conn)
        salida, sin_historia = [], 0
        for producto, nombre in producibles.items():
            try:
                saldo = disponibilidad.get_availability(product_id=producto, branch_id=branch_id)
                posicion = InventoryPosition(
                    product_id=producto, branch_id=branch_id,
                    current_stock=max(Decimal(str(saldo.on_hand)), Decimal("0")),
                    reserved=max(Decimal(str(saldo.reserved)), Decimal("0")),
                    incoming_stock=Decimal("0"), incoming_arrival_date=None,
                    supplier_lead_time_days=0)
                recomendacion = motor.recommend_production(
                    position=posicion, horizon_days=self.HORIZON_DAYS, as_of=self._today,
                    overstock_threshold_days=self.OVERSTOCK_DAYS,
                    target_coverage_days=self.COVERAGE_DAYS, confidence=self.CONFIDENCE,
                    valid_until=self._today + timedelta(days=self.HORIZON_DAYS))
            except Exception:  # noqa: BLE001 — sin historia suficiente para pronosticar
                sin_historia += 1
                continue
            if recomendacion is None or recomendacion.recommended_production_quantity <= 0:
                continue
            salida.append(PlanSuggestion(
                product_id=producto, product_name=nombre,
                quantity=Decimal(str(recomendacion.recommended_production_quantity)),
                source_type="FORECAST", source_reference_id=None,
                detail=_detalle_pronostico(recomendacion)))
        if not salida:
            self.note = ("El pronóstico no recomienda producir hoy"
                         + (f" ({sin_historia} producto(s) sin historia de ventas suficiente)"
                            if sin_historia else "") + ".")
        return salida
