from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.application.forecasting.services.forecast_runner import ForecastRunner
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import ScopePolicy, TimeGrain
from backend.domain.forecasting.enums import (
    ForecastModelFamily,
    ForecastModelStatus,
    ForecastRunStatus,
)
from backend.domain.forecasting.exceptions import ForecastModelNotApprovedError
from backend.domain.forecasting.value_objects.forecast_backtest import (
    ForecastAccuracyMetrics,
    ForecastBacktest,
)
from backend.domain.forecasting.value_objects.forecast_model_definition import (
    ForecastModelDefinition,
)
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)
from backend.shared.ids import new_uuid


class _FakeReader:
    def __init__(self, value: Decimal):
        self._value = value

    def read_observations(self, series_key, dimension_filter, date_from, date_to):
        observations = []
        current = date_from
        while current <= date_to:
            observations.append(TimeSeriesObservation(timestamp=current, value=self._value))
            current += timedelta(days=1)
        return tuple(observations)


class _FakeRunRepository:
    def __init__(self):
        self.saved = []

    def save_run(self, run, result):
        self.saved.append((run, result))

    def get_run(self, run_id):
        raise NotImplementedError

    def get_result(self, run_id):
        raise NotImplementedError

    def list_runs(self, series_key, limit=20):
        raise NotImplementedError


def _series_definition() -> TimeSeriesDefinition:
    return TimeSeriesDefinition(
        key="daily_sales_by_product", name="X", dimension_keys=("product",),
        time_grain=TimeGrain.DAILY, value_unit="unidades", minimum_history_days=5,
    )


def _model(status=ForecastModelStatus.ACTIVE, approved_at=datetime(2026, 9, 1, tzinfo=timezone.utc)):
    return ForecastModelDefinition(
        id=new_uuid(), model_key="naive_default", model_family=ForecastModelFamily.NAIVE,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc), status=status, version=1,
        approved_at=approved_at,
    )


def _backtest(model) -> ForecastBacktest:
    return ForecastBacktest(
        id=new_uuid(), model_key=model.model_key, model_version=model.version,
        series_definition_key="daily_sales_by_product",
        train_from=date(2026, 7, 1), train_to=date(2026, 8, 31),
        test_from=date(2026, 9, 1), test_to=date(2026, 9, 7),
        metrics=ForecastAccuracyMetrics(
            mae=Decimal("1"), rmse=Decimal("2"), mape=None, smape=None,
            wape=Decimal("10"), bias=Decimal("0"), mase=None,
        ),
        evaluated_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )


def test_run_persists_a_completed_run_and_result():
    reader = _FakeReader(Decimal("10"))
    builder = TimeSeriesDatasetBuilder(reader)
    repo = _FakeRunRepository()
    runner = ForecastRunner(builder, repo)
    model = _model()
    backtest = _backtest(model)

    run, result = runner.run(
        run_id=new_uuid(), model=model, reference_backtest=backtest,
        series_definition=_series_definition(), dimension_filter={"product": "p1"},
        scope_policy=ScopePolicy.BRANCH, scope_value="branch-1",
        training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
        forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 13),
        confidence_level=Decimal("0.90"), generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        clamp_min=Decimal("0"),
    )

    assert run.status == ForecastRunStatus.COMPLETED
    assert len(result.points) == 3
    assert all(p.point_forecast == Decimal("10") for p in result.points)
    assert repo.saved == [(run, result)]


def test_run_rejects_non_active_model():
    reader = _FakeReader(Decimal("10"))
    builder = TimeSeriesDatasetBuilder(reader)
    repo = _FakeRunRepository()
    runner = ForecastRunner(builder, repo)
    model = _model(status=ForecastModelStatus.TESTING, approved_at=None)
    backtest = _backtest(model)

    with pytest.raises(ForecastModelNotApprovedError):
        runner.run(
            run_id=new_uuid(), model=model, reference_backtest=backtest,
            series_definition=_series_definition(), dimension_filter={"product": "p1"},
            scope_policy=ScopePolicy.BRANCH, scope_value="branch-1",
            training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
            forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 13),
            confidence_level=Decimal("0.90"), generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        )


def test_run_rejects_backtest_for_a_different_model():
    reader = _FakeReader(Decimal("10"))
    builder = TimeSeriesDatasetBuilder(reader)
    repo = _FakeRunRepository()
    runner = ForecastRunner(builder, repo)
    model = _model()
    other_model = _model()
    mismatched_backtest = _backtest(other_model)
    # give it a different model_key so it clearly doesn't belong to `model`
    mismatched_backtest = ForecastBacktest(
        id=mismatched_backtest.id, model_key="some_other_model", model_version=1,
        series_definition_key=mismatched_backtest.series_definition_key,
        train_from=mismatched_backtest.train_from, train_to=mismatched_backtest.train_to,
        test_from=mismatched_backtest.test_from, test_to=mismatched_backtest.test_to,
        metrics=mismatched_backtest.metrics, evaluated_at=mismatched_backtest.evaluated_at,
    )

    with pytest.raises(ValueError):
        runner.run(
            run_id=new_uuid(), model=model, reference_backtest=mismatched_backtest,
            series_definition=_series_definition(), dimension_filter={"product": "p1"},
            scope_policy=ScopePolicy.BRANCH, scope_value="branch-1",
            training_from=date(2026, 8, 1), training_to=date(2026, 8, 10),
            forecast_from=date(2026, 8, 11), forecast_to=date(2026, 8, 13),
            confidence_level=Decimal("0.90"), generated_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
        )
