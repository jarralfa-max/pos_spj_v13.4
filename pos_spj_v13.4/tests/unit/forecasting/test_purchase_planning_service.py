from datetime import date, timedelta
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


class _FakeFinanceQueryPort:
    def __init__(self, cost_per_unit: Decimal):
        self.cost_per_unit = cost_per_unit
        self.calls = []

    def estimate_purchase_cost(self, product_id, quantity, branch_id):
        self.calls.append((product_id, quantity, branch_id))
        return quantity * self.cost_per_unit


def _series_definition() -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key="daily_sales_by_product", name="X", dimension_keys=("product", "branch"),
        time_grain=TimeGrain.DAILY, value_unit="unidades", minimum_history_days=14,
    )


def _build_services(demand_value: Decimal, cost_port=None):
    builder = TimeSeriesDatasetBuilder(_ConstantReader(demand_value))
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())
    purchase_service = PurchasePlanningService(
        inventory_service, builder, _series_definition(), cost_estimator=cost_port)
    return purchase_service


def test_recommends_purchase_when_reorder_point_is_crossed():
    service = _build_services(Decimal("10"))
    position = InventoryPosition(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )
    rec = service.recommend_purchase(
        position=position, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )
    assert rec is not None
    assert rec.product_id == "p1"
    # safety_stock=20, reorder_point=10*3+20=50; suggested = 50+7*10-100 = 20
    assert rec.safety_stock == Decimal("20")
    assert rec.suggested_quantity == Decimal("20")
    assert rec.estimated_cost is None  # no cost port injected


def test_returns_none_when_no_purchase_is_needed():
    service = _build_services(Decimal("1"))
    position = InventoryPosition(
        product_id="p1", branch_id="b1", current_stock=Decimal("10000"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )
    rec = service.recommend_purchase(
        position=position, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("1000"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )
    assert rec is None


def test_uses_injected_finance_port_for_estimated_cost():
    cost_port = _FakeFinanceQueryPort(cost_per_unit=Decimal("5"))
    service = _build_services(Decimal("10"), cost_port=cost_port)
    position = InventoryPosition(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )
    rec = service.recommend_purchase(
        position=position, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), target_coverage_days=Decimal("7"),
        confidence=Decimal("0.8"), valid_until=date(2026, 12, 10),
        safety_stock_method=SafetyStockMethod.FIXED_DAYS, fixed_days=Decimal("2"),
    )
    assert rec is not None
    assert rec.estimated_cost == rec.suggested_quantity * Decimal("5")
    assert cost_port.calls == [("p1", rec.suggested_quantity, "b1")]
