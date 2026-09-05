from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.application.scenario_planning.services.scaled_time_series_reader import (
    ScaledTimeSeriesReader,
)
from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation


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


def test_scales_every_observed_value():
    reader = ScaledTimeSeriesReader(_ConstantReader(Decimal("10")), factor=Decimal("1.5"))
    obs = reader.read_observations("s", {}, date(2026, 9, 1), date(2026, 9, 2))
    assert all(o.value == Decimal("15.0") for o in obs)


def test_preserves_imputation_metadata():
    class _ImputedReader:
        def read_observations(self, series_key, dimension_filter, date_from, date_to):
            return (TimeSeriesObservation(timestamp=date_from, value=Decimal("0"),
                                           is_imputed=True, imputation_reason="no_sales_recorded"),)

    reader = ScaledTimeSeriesReader(_ImputedReader(), factor=Decimal("2"))
    obs = reader.read_observations("s", {}, date(2026, 9, 1), date(2026, 9, 1))
    assert obs[0].is_imputed is True
    assert obs[0].imputation_reason == "no_sales_recorded"
    assert obs[0].value == Decimal("0")


def test_rejects_negative_factor():
    with pytest.raises(ValueError):
        ScaledTimeSeriesReader(_ConstantReader(Decimal("10")), factor=Decimal("-1"))


def test_factor_of_one_is_a_no_op():
    reader = ScaledTimeSeriesReader(_ConstantReader(Decimal("7")), factor=Decimal("1"))
    obs = reader.read_observations("s", {}, date(2026, 9, 1), date(2026, 9, 1))
    assert obs[0].value == Decimal("7")
