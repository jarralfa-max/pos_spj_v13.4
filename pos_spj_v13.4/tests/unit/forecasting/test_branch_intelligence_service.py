from datetime import date, timedelta
from decimal import Decimal

from backend.application.forecasting.services.branch_intelligence_service import (
    BranchIntelligenceService,
)
from backend.application.forecasting.services.demand_planning_service import (
    DemandPlanningService,
)
from backend.application.forecasting.services.inventory_forecast_service import (
    InventoryForecastService,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.enums import RecommendationPriority, SafetyStockMethod
from backend.domain.forecasting.value_objects.branch_recommendation import (
    BranchRecommendationType,
)
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)


class _ByProductReader:
    def __init__(self, demand_by_product: dict[str, Decimal]):
        self._demand = demand_by_product

    def read_observations(self, series_key, dimension_filter, date_from, date_to):
        value = self._demand[dimension_filter["product"]]
        observations = []
        current = date_from
        while current <= date_to:
            observations.append(TimeSeriesObservation(timestamp=current, value=value))
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


def _build_branch_service(demand_by_product: dict[str, Decimal]):
    # each call to DemandPlanningService/InventoryForecastService creates its
    # own model bootstrap keyed by "demand_planning_default" per product+branch
    # combo isn't distinguished by model_key in this pipeline (BI-12's design),
    # but the underlying reader IS keyed by product, which is all this test needs.
    builder = TimeSeriesDatasetBuilder(_ByProductReader(demand_by_product))
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())
    return BranchIntelligenceService(inventory_service, builder, _series_definition())


def _position(product_id, branch_id, current_stock) -> InventoryPosition:
    return InventoryPosition(
        product_id=product_id, branch_id=branch_id, current_stock=current_stock,
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )


def test_recommends_increase_stock_when_stockout_share_dominates():
    demand_by_product = {"p_stockout1": Decimal("20"), "p_stockout2": Decimal("20"),
                          "p_normal": Decimal("10")}
    service = _build_branch_service(demand_by_product)
    positions = (
        _position("p_stockout1", "b1", Decimal("50")),
        _position("p_stockout2", "b1", Decimal("50")),
        _position("p_normal", "b1", Decimal("100")),
    )
    rec = service.analyze_stock_risk(
        branch_id="b1", positions=positions, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), confidence=Decimal("0.8"),
        valid_until=date(2026, 12, 10), safety_stock_method=SafetyStockMethod.FIXED_DAYS,
        fixed_days=Decimal("2"),
    )
    assert rec is not None
    assert rec.recommendation_type == BranchRecommendationType.INCREASE_STOCK
    assert set(rec.affected_product_ids) == {"p_stockout1", "p_stockout2"}
    assert rec.priority == RecommendationPriority.CRITICAL  # 2/3 = 0.667 >= 0.6


def test_recommends_reduce_stock_when_overstock_share_dominates():
    demand_by_product = {"p_over1": Decimal("1"), "p_over2": Decimal("1"),
                          "p_normal": Decimal("10")}
    service = _build_branch_service(demand_by_product)
    positions = (
        _position("p_over1", "b1", Decimal("1000")),
        _position("p_over2", "b1", Decimal("1000")),
        _position("p_normal", "b1", Decimal("100")),
    )
    rec = service.analyze_stock_risk(
        branch_id="b1", positions=positions, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), confidence=Decimal("0.8"),
        valid_until=date(2026, 12, 10), safety_stock_method=SafetyStockMethod.FIXED_DAYS,
        fixed_days=Decimal("2"),
    )
    assert rec is not None
    assert rec.recommendation_type == BranchRecommendationType.REDUCE_STOCK
    assert set(rec.affected_product_ids) == {"p_over1", "p_over2"}


def test_no_recommendation_when_all_products_are_healthy():
    demand_by_product = {"p1": Decimal("10"), "p2": Decimal("10"), "p3": Decimal("10")}
    service = _build_branch_service(demand_by_product)
    positions = tuple(_position(p, "b1", Decimal("100")) for p in ("p1", "p2", "p3"))
    rec = service.analyze_stock_risk(
        branch_id="b1", positions=positions, horizon_days=5, as_of=date(2026, 12, 1),
        overstock_threshold_days=Decimal("30"), confidence=Decimal("0.8"),
        valid_until=date(2026, 12, 10), safety_stock_method=SafetyStockMethod.FIXED_DAYS,
        fixed_days=Decimal("2"),
    )
    assert rec is None


def test_recommend_transfer_from_surplus_branch_to_deficit_branch():
    demand_by_product = {"p1": Decimal("1")}  # source demand; overridden per-branch below
    service = _build_branch_service(demand_by_product)
    source = _position("p1", "b_source", Decimal("1000"))
    destination = _position("p1", "b_dest", Decimal("30"))

    # patch reader to vary demand by branch too, since source/destination need
    # different demand profiles for a realistic surplus/deficit scenario
    class _ByBranchReader:
        def read_observations(self, series_key, dimension_filter, date_from, date_to):
            value = Decimal("1") if dimension_filter.get("branch") == "b_source" else Decimal("20")
            observations = []
            current = date_from
            while current <= date_to:
                observations.append(TimeSeriesObservation(timestamp=current, value=value))
                current += timedelta(days=1)
            return tuple(observations)

    builder = TimeSeriesDatasetBuilder(_ByBranchReader())
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())
    service = BranchIntelligenceService(inventory_service, builder, _series_definition())

    rec = service.recommend_transfer(
        product_id="p1", source_position=source, destination_position=destination,
        horizon_days=5, as_of=date(2026, 12, 1), overstock_threshold_days=Decimal("30"),
        target_coverage_days=Decimal("7"), confidence=Decimal("0.8"),
        valid_until=date(2026, 12, 10), safety_stock_method=SafetyStockMethod.FIXED_DAYS,
        fixed_days=Decimal("2"),
    )
    assert rec is not None
    assert rec.source_branch_id == "b_source"
    assert rec.destination_branch_id == "b_dest"
    # destination: safety_stock=2*20=40, reorder_point=20*3+40=100
    # destination_need = 100 + 7*20 - 30 = 210; source_surplus = 1000 - (1*3+2) = 995
    assert rec.suggested_quantity == Decimal("210")


def test_recommend_transfer_returns_none_when_source_has_no_surplus():
    class _BothLowReader:
        def read_observations(self, series_key, dimension_filter, date_from, date_to):
            observations = []
            current = date_from
            while current <= date_to:
                observations.append(TimeSeriesObservation(timestamp=current, value=Decimal("20")))
                current += timedelta(days=1)
            return tuple(observations)

    builder = TimeSeriesDatasetBuilder(_BothLowReader())
    demand_service = DemandPlanningService(
        builder, _FakeModelRepository(), _FakeRunRepository(), _series_definition())
    inventory_service = InventoryForecastService(demand_service, builder, _series_definition())
    service = BranchIntelligenceService(inventory_service, builder, _series_definition())

    source = _position("p1", "b_source", Decimal("50"))  # also short on stock, no surplus
    destination = _position("p1", "b_dest", Decimal("30"))
    rec = service.recommend_transfer(
        product_id="p1", source_position=source, destination_position=destination,
        horizon_days=5, as_of=date(2026, 12, 1), overstock_threshold_days=Decimal("30"),
        target_coverage_days=Decimal("7"), confidence=Decimal("0.8"),
        valid_until=date(2026, 12, 10), safety_stock_method=SafetyStockMethod.FIXED_DAYS,
        fixed_days=Decimal("2"),
    )
    assert rec is None
