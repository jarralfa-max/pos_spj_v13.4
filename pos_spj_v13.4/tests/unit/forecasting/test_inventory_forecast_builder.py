from datetime import date, timedelta
from decimal import Decimal

from backend.domain.forecasting.services.inventory_forecast_builder import (
    build_inventory_forecast,
)
from backend.domain.forecasting.value_objects.forecast_run import ForecastResult, ForecastResultPoint
from backend.domain.forecasting.value_objects.inventory_forecast import InventoryPosition
from backend.shared.ids import new_uuid

_START = date(2026, 9, 1)


def _result(triples: list[tuple[str, str, str]]) -> ForecastResult:
    points = tuple(
        ForecastResultPoint(
            timestamp=_START + timedelta(days=i),
            point_forecast=Decimal(p), lower_bound=Decimal(lo), upper_bound=Decimal(hi),
        )
        for i, (p, lo, hi) in enumerate(triples)
    )
    return ForecastResult(run_id=new_uuid(), points=points)


def _position(**overrides) -> InventoryPosition:
    fields = dict(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=2,
    )
    fields.update(overrides)
    return InventoryPosition(**fields)


def test_happy_path_reorder_date_when_projected_stock_crosses_reorder_point():
    demand = _result([("20", "15", "25"), ("20", "15", "25"), ("20", "15", "25")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("100")),
        safety_stock_qty=Decimal("10"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("10"), recent_avg_daily_demand=Decimal("20"),
    )
    # reorder_point = 20*2 + 10 = 50
    assert forecast.reorder_point == Decimal("50")
    # projected stock: 80, 60, 40 -> crosses <=50 on day 3
    assert [p.projected_stock for p in forecast.points] == [Decimal("80"), Decimal("60"), Decimal("40")]
    assert forecast.reorder_date == _START + timedelta(days=2)
    assert all(p.stockout_probability == Decimal("0") for p in forecast.points)
    assert all(p.overstock_probability == Decimal("0") for p in forecast.points)


def test_reorder_date_is_none_when_never_crossed():
    demand = _result([("1", "0", "2"), ("1", "0", "2")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("1000")),
        safety_stock_qty=Decimal("10"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("100"), recent_avg_daily_demand=Decimal("1"),
    )
    assert forecast.reorder_date is None


def test_stockout_probability_is_one_when_point_forecast_depletes_stock():
    demand = _result([("60", "55", "65")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("50")),
        safety_stock_qty=Decimal("0"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("100"), recent_avg_daily_demand=Decimal("50"),
    )
    assert forecast.points[0].projected_stock == Decimal("-10")
    assert forecast.points[0].stockout_probability == Decimal("1")


def test_stockout_probability_is_partial_when_only_upper_bound_breaches():
    demand = _result([("60", "55", "75")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("70")),
        safety_stock_qty=Decimal("0"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("100"), recent_avg_daily_demand=Decimal("60"),
    )
    # point scenario: 70-60=10 (>=0, not stockout by point)
    # high-demand scenario: 70-75=-5 (<0) -> partial risk = complement
    assert forecast.points[0].projected_stock == Decimal("10")
    assert forecast.points[0].stockout_probability == Decimal("0.10")


def test_overstock_probability_is_one_when_point_forecast_exceeds_threshold():
    demand = _result([("5", "2", "8")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("500")),
        safety_stock_qty=Decimal("0"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("5"), recent_avg_daily_demand=Decimal("20"),
    )
    # threshold = 5*20=100; projected = 500-5=495 > 100
    assert forecast.points[0].overstock_probability == Decimal("1")


def test_overstock_probability_is_partial_when_only_low_demand_scenario_exceeds():
    demand = _result([("60", "40", "80")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("150")),
        safety_stock_qty=Decimal("0"), confidence_level_complement=Decimal("0.15"),
        overstock_threshold_days=Decimal("5"), recent_avg_daily_demand=Decimal("20"),
    )
    # threshold=100; point scenario: 150-60=90 (not > 100)
    # low-demand scenario: 150-40=110 (>100) -> partial risk
    assert forecast.points[0].projected_stock == Decimal("90")
    assert forecast.points[0].overstock_probability == Decimal("0.15")


def test_incoming_stock_arrives_on_its_arrival_date_not_before():
    demand = _result([("5", "3", "7"), ("5", "3", "7")])
    forecast = build_inventory_forecast(
        demand_result=demand,
        position=_position(current_stock=Decimal("10"), incoming_stock=Decimal("50"),
                            incoming_arrival_date=_START + timedelta(days=1)),
        safety_stock_qty=Decimal("0"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("100"), recent_avg_daily_demand=Decimal("5"),
    )
    # day 1 (before arrival): 10 - 5 = 5
    assert forecast.points[0].projected_stock == Decimal("5")
    # day 2 (arrival day): 10 + 50 - (5+5) = 50
    assert forecast.points[1].projected_stock == Decimal("50")


def test_days_of_supply_is_none_when_no_recent_demand():
    demand = _result([("0", "0", "0")])
    forecast = build_inventory_forecast(
        demand_result=demand, position=_position(current_stock=Decimal("100")),
        safety_stock_qty=Decimal("0"), confidence_level_complement=Decimal("0.10"),
        overstock_threshold_days=Decimal("100"), recent_avg_daily_demand=Decimal("0"),
    )
    assert forecast.points[0].days_of_supply is None
