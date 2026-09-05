from datetime import date
from decimal import Decimal

import pytest

from backend.domain.forecasting.value_objects.inventory_forecast import (
    InventoryForecast,
    InventoryForecastPoint,
    InventoryPosition,
)


def _position(**overrides) -> InventoryPosition:
    fields = dict(
        product_id="p1", branch_id="b1", current_stock=Decimal("100"),
        reserved=Decimal("0"), incoming_stock=Decimal("0"), incoming_arrival_date=None,
        supplier_lead_time_days=3,
    )
    fields.update(overrides)
    return InventoryPosition(**fields)


def test_available_stock_subtracts_reserved():
    position = _position(current_stock=Decimal("100"), reserved=Decimal("30"))
    assert position.available_stock() == Decimal("70")


def test_rejects_negative_current_stock():
    with pytest.raises(ValueError):
        _position(current_stock=Decimal("-1"))


def test_rejects_incoming_stock_without_arrival_date():
    with pytest.raises(ValueError):
        _position(incoming_stock=Decimal("10"), incoming_arrival_date=None)


def test_rejects_negative_lead_time():
    with pytest.raises(ValueError):
        _position(supplier_lead_time_days=-1)


def _point(**overrides) -> InventoryForecastPoint:
    fields = dict(
        date=date(2026, 9, 1), projected_stock=Decimal("50"), days_of_supply=Decimal("5"),
        stockout_probability=Decimal("0"), overstock_probability=Decimal("0"),
    )
    fields.update(overrides)
    return InventoryForecastPoint(**fields)


def test_probability_must_be_in_0_1_range():
    with pytest.raises(ValueError):
        _point(stockout_probability=Decimal("1.5"))
    with pytest.raises(ValueError):
        _point(overstock_probability=Decimal("-0.1"))


def test_inventory_forecast_requires_sorted_points():
    ordered = (_point(date=date(2026, 9, 1)), _point(date=date(2026, 9, 2)))
    InventoryForecast(product_id="p1", branch_id="b1", safety_stock=Decimal("10"),
                       reorder_point=Decimal("20"), reorder_date=None, points=ordered)

    unordered = (_point(date=date(2026, 9, 2)), _point(date=date(2026, 9, 1)))
    with pytest.raises(ValueError):
        InventoryForecast(product_id="p1", branch_id="b1", safety_stock=Decimal("10"),
                           reorder_point=Decimal("20"), reorder_date=None, points=unordered)


def test_inventory_forecast_rejects_empty_points():
    with pytest.raises(ValueError):
        InventoryForecast(product_id="p1", branch_id="b1", safety_stock=Decimal("10"),
                           reorder_point=Decimal("20"), reorder_date=None, points=())
