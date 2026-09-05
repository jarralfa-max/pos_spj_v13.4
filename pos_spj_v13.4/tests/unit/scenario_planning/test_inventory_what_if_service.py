from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.application.forecasting.services.demand_planning_service import (
    DemandPlanningService,
)
from backend.application.forecasting.services.inventory_forecast_service import (
    InventoryForecastService,
)
from backend.application.forecasting.services.purchase_planning_service import (
    PurchasePlanningService,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.application.scenario_planning.services.inventory_what_if_service import (
    InventoryWhatIfService,
)
from backend.application.scenario_planning.services.scaled_time_series_reader import (
    ScaledTimeSeriesReader,
)
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)
from backend.domain.scenario_planning.enums import ScenarioVariableKind
from backend.domain.scenario_planning.value_objects.scenario import (
    BusinessScenario,
    ScenarioVariable,
)
from backend.shared.ids import new_uuid


class _ConstantReader:
    def __init__(self, value: Decimal):
        self._value = value

    def read_observations(self, series_key, dimension_filter, date_from, date_to):
        observations = []
        current = date_from
        while current <= date_to:
            observations.append(TimeSeriesObservation(timestamp=current, value=self._value))
            current += timedelta(days=1)
        return tuple(observations)


class _FakeModelRepository:
    def __init__(self):
        self._by_key = {}

    def save(self, definition):
        self._by_key[definition.model_key] = definition

    def get(self, model_key, version):
        raise NotImplementedError

    def get_active(self, model_key):
        model = self._by_key.get(model_key)
        return model if model is not None and model.status.value == "ACTIVE" else None

    def list_versions(self, model_key):
        raise NotImplementedError


class _FakeRunRepository:
    def save_run(self, run, result):
        pass

    def get_run(self, run_id):
        raise NotImplementedError

    def get_result(self, run_id):
        raise NotImplementedError

    def list_runs(self, series_key, limit=20):
        raise NotImplementedError


def _series_definition() -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key="daily_sales_by_product", name="X", dimension_keys=("product", "branch"),
        time_grain=TimeGrain.DAILY, value_unit="unidades", minimum_history_days=14,
    )


def _purchase_service(reader) -> PurchasePlanningService:
    builder = TimeSeriesDatasetBuilder(reader)
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())
    return PurchasePlanningService(inventory_service, builder, _series_definition())


def test_simulate_demand_increase_raises_the_suggested_purchase_quantity():
    real_reader = _ConstantReader(Decimal("10"))
    baseline_service = _purchase_service(real_reader)
    scenario_service = _purchase_service(ScaledTimeSeriesReader(real_reader, factor=Decimal("1.5")))

    scenario = BusinessScenario(
        id=new_uuid(), name="Demanda +50%",
        variables=(ScenarioVariable(kind=ScenarioVariableKind.DEMAND_CHANGE_PCT,
                                     value=Decimal("50")),),
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    position = InventoryPosition(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )

    what_if = InventoryWhatIfService()
    result = what_if.simulate_purchase_need(
        scenario=scenario, baseline_service=baseline_service, scenario_service=scenario_service,
        position=position, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )

    # baseline (demand=10): safety=20, reorder_point=50, suggested=50+70-100=20
    # scenario (demand=15): safety=30, reorder_point=75, suggested=75+105-100=80
    assert result.baseline_metrics["suggested_quantity"] == Decimal("20")
    assert result.scenario_metrics["suggested_quantity"] == Decimal("80")
    assert result.delta("suggested_quantity") == Decimal("60")
