from datetime import date
from decimal import Decimal

import pytest

from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.exceptions import InsufficientHistoryError
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)


class _FakeReader:
    def __init__(self, observations):
        self.observations = observations
        self.calls = []

    def read_observations(self, series_key, dimension_filter, date_from, date_to):
        self.calls.append((series_key, dimension_filter, date_from, date_to))
        return self.observations


def _definition(minimum_history_days=14) -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key="daily_sales_by_product", name="X", dimension_keys=("product", "branch"),
        time_grain=TimeGrain.DAILY, value_unit="unidades",
        minimum_history_days=minimum_history_days,
    )


def test_build_delegates_to_reader_and_returns_observations():
    obs = (TimeSeriesObservation(timestamp=date(2026, 8, 1), value=Decimal("5")),)
    reader = _FakeReader(obs)
    builder = TimeSeriesDatasetBuilder(reader)
    result = builder.build(_definition(), {"product": "p1"}, date(2026, 8, 1), date(2026, 8, 20))
    assert result == obs
    assert reader.calls[0][0] == "daily_sales_by_product"


def test_rejects_range_shorter_than_minimum_history_days():
    reader = _FakeReader(())
    builder = TimeSeriesDatasetBuilder(reader)
    with pytest.raises(InsufficientHistoryError):
        builder.build(_definition(minimum_history_days=14), {"product": "p1"},
                       date(2026, 8, 1), date(2026, 8, 5))


def test_rejects_date_to_before_date_from():
    reader = _FakeReader(())
    builder = TimeSeriesDatasetBuilder(reader)
    with pytest.raises(ValueError):
        builder.build(_definition(), {"product": "p1"}, date(2026, 8, 20), date(2026, 8, 1))


def test_rejects_dimension_filter_key_not_declared_by_definition():
    reader = _FakeReader(())
    builder = TimeSeriesDatasetBuilder(reader)
    with pytest.raises(ValueError):
        builder.build(_definition(), {"supplier": "s1"}, date(2026, 8, 1), date(2026, 8, 20))
