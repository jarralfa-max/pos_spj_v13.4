from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.application.forecasting.services.forecast_backtester import ForecastBacktester
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import TimeGrain
from backend.domain.forecasting.enums import ForecastModelFamily
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)
from backend.shared.ids import new_uuid


class _FakeReader:
    def __init__(self, values_by_date: dict[date, Decimal]):
        self._values = values_by_date

    def read_observations(self, series_key, dimension_filter, date_from, date_to):
        observations = []
        current = date_from
        while current <= date_to:
            observations.append(TimeSeriesObservation(timestamp=current, value=self._values[current]))
            current += timedelta(days=1)
        return tuple(observations)


def _series_definition() -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key="daily_sales_by_product", name="X", dimension_keys=("product",),
        time_grain=TimeGrain.DAILY, value_unit="unidades", minimum_history_days=5,
    )


def test_backtester_runs_naive_model_and_computes_metrics():
    train_from, train_to = date(2026, 8, 1), date(2026, 8, 10)
    test_from, test_to = date(2026, 8, 11), date(2026, 8, 13)

    values: dict[date, Decimal] = {}
    d = train_from
    while d <= train_to:
        values[d] = Decimal("10")
        d += timedelta(days=1)
    values[date(2026, 8, 11)] = Decimal("10")
    values[date(2026, 8, 12)] = Decimal("10")
    values[date(2026, 8, 13)] = Decimal("12")

    builder = TimeSeriesDatasetBuilder(_FakeReader(values))
    backtester = ForecastBacktester(builder)

    backtest = backtester.run(
        backtest_id=new_uuid(),
        series_definition=_series_definition(),
        dimension_filter={"product": "p1"},
        model_family=ForecastModelFamily.NAIVE,
        model_key="naive_default",
        model_version=1,
        train_from=train_from, train_to=train_to,
        test_from=test_from, test_to=test_to,
        evaluated_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )

    # NAIVE forecasts the last training value (10) flat for the 3-day horizon;
    # actuals are 10,10,12 -> errors 0,0,2 -> MAE = 2/3.
    assert backtest.metrics.mae == Decimal(2) / Decimal(3)
    assert backtest.model_key == "naive_default"
    assert backtest.series_definition_key == "daily_sales_by_product"
    assert backtest.train_from == train_from
    assert backtest.test_to == test_to


def test_backtester_test_window_is_not_gated_by_minimum_history():
    """The 3-day holdout is shorter than the series' minimum_history_days=5
    — must not raise InsufficientHistoryError for the test window."""
    train_from, train_to = date(2026, 8, 1), date(2026, 8, 10)
    test_from, test_to = date(2026, 8, 11), date(2026, 8, 12)
    values = {train_from + timedelta(days=i): Decimal("5") for i in range(10)}
    values[test_from] = Decimal("5")
    values[test_to] = Decimal("5")

    builder = TimeSeriesDatasetBuilder(_FakeReader(values))
    backtester = ForecastBacktester(builder)
    backtest = backtester.run(
        backtest_id=new_uuid(), series_definition=_series_definition(),
        dimension_filter={"product": "p1"}, model_family=ForecastModelFamily.NAIVE,
        model_key="naive_default", model_version=1,
        train_from=train_from, train_to=train_to, test_from=test_from, test_to=test_to,
        evaluated_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    assert backtest.metrics.mae == Decimal(0)
