"""ForecastRunner (§16/§24-25, BI-11) — produces a persisted ForecastRun +
ForecastResult from a series + an ACTIVE model + a reference backtest used
to size the confidence interval.

Refuses to run a model that isn't `ACTIVE` (§20-23: no forecast is served
off a model that hasn't cleared approval), and refuses a `reference_backtest`
that doesn't actually belong to the model being run — the confidence
interval must come from evidence about *this* model, not an unrelated one.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.domain.forecasting.exceptions import ForecastModelNotApprovedError
from backend.domain.forecasting.repository_ports import ForecastRunRepositoryPort
from backend.domain.forecasting.services.confidence_interval import build_bounds
from backend.domain.forecasting.services.model_dispatch import run_baseline_model
from backend.domain.forecasting.value_objects.forecast_backtest import ForecastBacktest
from backend.domain.forecasting.value_objects.forecast_model_definition import (
    ForecastModelDefinition,
)
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition


class ForecastRunner:
    def __init__(
        self,
        dataset_builder: TimeSeriesDatasetBuilder,
        run_repository: ForecastRunRepositoryPort,
    ) -> None:
        self._dataset_builder = dataset_builder
        self._run_repository = run_repository

    def run(
        self,
        *,
        run_id: str,
        model: ForecastModelDefinition,
        reference_backtest: ForecastBacktest,
        series_definition: TimeSeriesDefinition,
        dimension_filter: dict[str, str],
        scope_policy: ScopePolicy,
        scope_value: str,
        training_from: date,
        training_to: date,
        forecast_from: date,
        forecast_to: date,
        confidence_level: Decimal,
        generated_at: datetime,
        clamp_min: Decimal | None = None,
    ) -> tuple[ForecastRun, ForecastResult]:
        if not model.is_usable_for_forecasting():
            raise ForecastModelNotApprovedError(
                f"Model {model.model_key} v{model.version} is {model.status.value}, "
                "not ACTIVE — cannot serve a forecast off it"
            )
        if (reference_backtest.model_key, reference_backtest.model_version) != (
                model.model_key, model.version):
            raise ValueError(
                "reference_backtest does not belong to the model being run "
                f"({reference_backtest.model_key} v{reference_backtest.model_version} != "
                f"{model.model_key} v{model.version})"
            )

        observations = self._dataset_builder.build(
            series_definition, dimension_filter, training_from, training_to)
        horizon_days = (forecast_to - forecast_from).days + 1
        point_forecasts = run_baseline_model(
            model.model_family, observations, horizon_days, model.parameters)
        bounds = build_bounds(
            point_forecasts, reference_backtest.metrics.rmse, confidence_level, clamp_min)

        run = ForecastRun(
            run_id=run_id,
            model_version_id=model.id,
            series_definition_key=series_definition.key,
            scope_policy=scope_policy,
            scope_value=scope_value,
            training_from=training_from,
            training_to=training_to,
            forecast_from=forecast_from,
            forecast_to=forecast_to,
            horizon_days=horizon_days,
            generated_at=generated_at,
            confidence_level=confidence_level,
            status=ForecastRunStatus.COMPLETED,
        )
        points = tuple(
            ForecastResultPoint(
                timestamp=forecast_from + timedelta(days=h),
                point_forecast=point_forecasts[h],
                lower_bound=bounds[h][0],
                upper_bound=bounds[h][1],
            )
            for h in range(horizon_days)
        )
        result = ForecastResult(run_id=run_id, points=points)
        self._run_repository.save_run(run, result)
        return run, result
