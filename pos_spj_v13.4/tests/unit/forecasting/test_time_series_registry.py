import pytest

from backend.application.forecasting.services.time_series_registry import TimeSeriesRegistry
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.exceptions import TimeSeriesNotFoundError
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition


def _series(key="daily_sales_by_product") -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key=key, name="X", dimension_keys=("product",), time_grain=TimeGrain.DAILY,
        value_unit="unidades", minimum_history_days=14,
    )


def test_register_and_get_round_trip():
    registry = TimeSeriesRegistry()
    registry.register(_series())
    assert registry.get("daily_sales_by_product").key == "daily_sales_by_product"


def test_get_unknown_series_raises_time_series_not_found_error():
    registry = TimeSeriesRegistry()
    with pytest.raises(TimeSeriesNotFoundError):
        registry.get("does_not_exist")


def test_registering_duplicate_key_is_rejected():
    registry = TimeSeriesRegistry()
    registry.register(_series())
    with pytest.raises(ValueError):
        registry.register(_series())


def test_all_returns_every_registered_definition():
    registry = TimeSeriesRegistry()
    registry.register(_series("a"))
    registry.register(_series("b"))
    assert {s.key for s in registry.all()} == {"a", "b"}
