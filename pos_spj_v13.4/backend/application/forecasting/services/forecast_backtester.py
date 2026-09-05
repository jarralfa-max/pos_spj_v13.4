"""ForecastBacktester (§22, BI-10) — evaluates one baseline model against a
held-out (out-of-sample) window and produces a `ForecastBacktest`.

Trains on `[train_from, train_to]` via `TimeSeriesDatasetBuilder.build()`
(minimum-history gated), forecasts `horizon = (test_to - test_from) + 1`
days ahead with the requested `ForecastModelFamily`, then compares against
the real observations of `[test_from, test_to]` (fetched via
`build_test_window()`, not history-gated) using every metric in
`accuracy_metrics`.
"""

from __future__ import annotations

from datetime import date, datetime

from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.forecasting.enums import ForecastModelFamily
from backend.domain.forecasting.services import accuracy_metrics
from backend.domain.forecasting.services.model_dispatch import run_baseline_model
from backend.domain.forecasting.value_objects.forecast_backtest import (
    ForecastAccuracyMetrics,
    ForecastBacktest,
)
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition


class ForecastBacktester:
    def __init__(self, dataset_builder: TimeSeriesDatasetBuilder) -> None:
        self._dataset_builder = dataset_builder

    def run(
        self,
        *,
        backtest_id: str,
        series_definition: TimeSeriesDefinition,
        dimension_filter: dict[str, str],
        model_family: ForecastModelFamily,
        model_key: str,
        model_version: int,
        train_from: date,
        train_to: date,
        test_from: date,
        test_to: date,
        evaluated_at: datetime,
        parameters: dict | None = None,
    ) -> ForecastBacktest:
        train_observations = self._dataset_builder.build(
            series_definition, dimension_filter, train_from, train_to)
        test_observations = self._dataset_builder.build_test_window(
            series_definition, dimension_filter, test_from, test_to)

        horizon_days = (test_to - test_from).days + 1
        forecast = run_baseline_model(
            model_family, train_observations, horizon_days, parameters)
        actual = tuple(obs.value for obs in test_observations)
        training_history = tuple(obs.value for obs in train_observations)

        metrics = ForecastAccuracyMetrics(
            mae=accuracy_metrics.mae(actual, forecast),
            rmse=accuracy_metrics.rmse(actual, forecast),
            mape=accuracy_metrics.mape(actual, forecast),
            smape=accuracy_metrics.smape(actual, forecast),
            wape=accuracy_metrics.wape(actual, forecast),
            bias=accuracy_metrics.bias(actual, forecast),
            mase=accuracy_metrics.mase(actual, forecast, training_history),
        )
        return ForecastBacktest(
            id=backtest_id,
            model_key=model_key,
            model_version=model_version,
            series_definition_key=series_definition.key,
            train_from=train_from,
            train_to=train_to,
            test_from=test_from,
            test_to=test_to,
            metrics=metrics,
            evaluated_at=evaluated_at,
        )
