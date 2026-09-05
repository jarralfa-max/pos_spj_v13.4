from datetime import date, timedelta
from decimal import Decimal

from backend.application.forecasting.services.demand_planning_service import (
    DemandPlanningService,
)
from backend.application.forecasting.services.inventory_forecast_service import (
    InventoryForecastService,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition


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


def test_forecast_inventory_end_to_end_with_constant_demand():
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("10")))
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())

    position = InventoryPosition(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )

    forecast = inventory_service.forecast_inventory(
        position=position, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )

    assert forecast.product_id == "p1"
    # constant demand=10/day, safety_stock = 10*2 = 20, reorder_point = 10*3+20=50
    assert forecast.safety_stock == Decimal("20")
    assert forecast.reorder_point == Decimal("50")
    # projected stock after day5: 100 - 5*10 = 50 (exactly at reorder point)
    assert forecast.points[-1].projected_stock == Decimal("50")
    assert forecast.reorder_date == date(2026, 12, 5)
