from datetime import date, timedelta
from decimal import Decimal

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
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)


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


class _FakeCapacityPort:
    def __init__(self, yield_pct: Decimal, capacity: Decimal):
        self.yield_pct = yield_pct
        self.capacity = capacity
        self.calls = []

    def expected_yield_pct(self, product_id, branch_id):
        self.calls.append(("yield", product_id, branch_id))
        return self.yield_pct

    def available_capacity(self, branch_id, as_of):
        self.calls.append(("capacity", branch_id, as_of))
        return self.capacity


def _series_definition() -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key="daily_sales_by_product", name="X", dimension_keys=("product", "branch"),
        time_grain=TimeGrain.DAILY, value_unit="unidades", minimum_history_days=14,
    )


def _build_services(demand_value: Decimal, capacity_port=None):
    builder = TimeSeriesDatasetBuilder(_ConstantReader(demand_value))
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())
    production_service = ProductionPlanningService(
        inventory_service, builder, _series_definition(), capacity_port=capacity_port)
    return production_service


def _position(**overrides) -> InventoryPosition:
    fields = dict(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )
    fields.update(overrides)
    return InventoryPosition(**fields)


def test_recommends_production_when_reorder_point_is_crossed():
    service = _build_services(Decimal("10"))
    rec = service.recommend_production(
        position=_position(), horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )
    assert rec is not None
    assert rec.recommended_production_quantity == Decimal("20")
    assert rec.expected_yield_pct is None
    assert rec.required_raw_material is None


def test_returns_none_when_no_production_is_needed():
    service = _build_services(Decimal("1"))
    rec = service.recommend_production(
        position=_position(current_stock=Decimal("10000")), horizon_days=5,
        as_of=date(2026, 12, 1), overstock_threshold_days=Decimal("1000"),
        target_coverage_days=Decimal("7"), confidence=Decimal("0.8"),
        valid_until=date(2026, 12, 10), safety_stock_method=SafetyStockMethod.FIXED_DAYS,
        fixed_days=Decimal("2"),
    )
    assert rec is None


def test_uses_capacity_port_for_yield_and_utilization():
    capacity_port = _FakeCapacityPort(yield_pct=Decimal("0.8"), capacity=Decimal("40"))
    service = _build_services(Decimal("10"), capacity_port=capacity_port)
    rec = service.recommend_production(
        position=_position(), horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )
    assert rec is not None
    # quantity=20, yield=0.8 -> required_raw_material = 20/0.8 = 25
    assert rec.required_raw_material == Decimal("25")
    # capacity=40 -> utilization = 20/40 = 0.5 -> 50%
    assert rec.capacity_utilization_pct == Decimal("50")
    assert ("yield", "p1", "b1") in capacity_port.calls


def test_capacity_utilization_is_capped_at_100_percent():
    capacity_port = _FakeCapacityPort(yield_pct=Decimal("1"), capacity=Decimal("5"))
    service = _build_services(Decimal("10"), capacity_port=capacity_port)
    rec = service.recommend_production(
        position=_position(), horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )
    assert rec.capacity_utilization_pct == Decimal("100")
