"""DemandPlanningService (§26, BI-12) — the first real consumer of the
ForecastingPlatform (BI-7..BI-11) against production data.

Forecasts demand for a product, optionally scoped to a branch (§26: "por
producto ... por sucursal"; by-category/by-channel wait for a series
definition with those dimensions wired to a real reader — not invented
speculatively here, same discipline as BI-8/BI-3).

Orchestration per call:
  1. get (or bootstrap) an `ACTIVE` model for `model_key`;
  2. run a FRESH backtest ending just before `as_of` — re-validating on
     every call keeps the confidence interval honest as new sales land,
     rather than trusting a stale RMSE from whenever the model was first
     approved;
  3. run `ForecastRunner` using that backtest as the confidence-interval
     evidence, training on the freshest `training_window_days` of data.

Bootstrap policy (documented caveat): if no `ACTIVE` model exists yet for
`model_key`, one is created and saved **directly as `ACTIVE`** — there is no
human-approval gate (DRAFT→TESTING→APPROVED) here. §136 ("toda
recomendación comienza como advisory only") applies to *recommendations*,
not to this forecast-generation step, but a real governance workflow (an
explicit approve step, minimum-confidence thresholds per §135) belongs in a
later phase once a UI/Use Case exists to drive it — this bootstrap exists
only so the pipeline is usable end-to-end today. Every call (bootstrap or
not) still runs a fresh backtest before forecasting, so the confidence
interval is always evidence-based even though activation itself isn't gated
yet.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.application.forecasting.services.forecast_backtester import ForecastBacktester
from backend.application.forecasting.services.forecast_runner import ForecastRunner
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastModelFamily, ForecastModelStatus
from backend.domain.forecasting.repository_ports import (
    ForecastModelRepositoryPort,
    ForecastRunRepositoryPort,
)
from backend.domain.forecasting.value_objects.forecast_model_definition import (
    ForecastModelDefinition,
)
from backend.domain.forecasting.value_objects.forecast_run import ForecastResult, ForecastRun
from backend.domain.forecasting.value_objects.time_series import TimeSeriesDefinition
from backend.shared.ids import new_uuid

_BACKTEST_HOLDOUT_DAYS = 7


class DemandPlanningService:
    def __init__(
        self,
        dataset_builder: TimeSeriesDatasetBuilder,
        model_repository: ForecastModelRepositoryPort,
        run_repository: ForecastRunRepositoryPort,
        series_definition: TimeSeriesDefinition,
        default_model_family: ForecastModelFamily = ForecastModelFamily.SES,
        default_confidence_level: Decimal = Decimal("0.90"),
    ) -> None:
        self._dataset_builder = dataset_builder
        self._model_repository = model_repository
        self._backtester = ForecastBacktester(dataset_builder)
        self._runner = ForecastRunner(dataset_builder, run_repository)
        self._series_definition = series_definition
        self._default_model_family = default_model_family
        self._default_confidence_level = default_confidence_level

    def forecast_product_demand(
        self,
        *,
        product_id: str,
        branch_id: str | None,
        horizon_days: int,
        as_of: date,
        model_key: str = "demand_planning_default",
    ) -> tuple[ForecastRun, ForecastResult]:
        if horizon_days <= 0:
            raise ValueError("horizon_days must be > 0")

        dimension_filter: dict[str, str] = {"product": product_id}
        if branch_id:
            dimension_filter["branch"] = branch_id
        scope_policy = ScopePolicy.BRANCH if branch_id else ScopePolicy.COMPANY
        scope_value = branch_id or "ALL_BRANCHES"

        model = self._model_repository.get_active(model_key)
        if model is None:
            model = self._bootstrap_model(model_key)

        test_to = as_of - timedelta(days=1)
        test_from = test_to - timedelta(days=_BACKTEST_HOLDOUT_DAYS - 1)
        backtest_train_to = test_from - timedelta(days=1)
        backtest_train_from = backtest_train_to - timedelta(days=model.training_window_days - 1)

        now = datetime.now(timezone.utc)
        backtest = self._backtester.run(
            backtest_id=new_uuid(),
            series_definition=self._series_definition,
            dimension_filter=dimension_filter,
            model_family=model.model_family,
            model_key=model.model_key,
            model_version=model.version,
            train_from=backtest_train_from,
            train_to=backtest_train_to,
            test_from=test_from,
            test_to=test_to,
            evaluated_at=now,
            parameters=model.parameters,
        )

        forecast_train_to = as_of - timedelta(days=1)
        forecast_train_from = forecast_train_to - timedelta(days=model.training_window_days - 1)
        forecast_from = as_of
        forecast_to = as_of + timedelta(days=horizon_days - 1)

        return self._runner.run(
            run_id=new_uuid(),
            model=model,
            reference_backtest=backtest,
            series_definition=self._series_definition,
            dimension_filter=dimension_filter,
            scope_policy=scope_policy,
            scope_value=scope_value,
            training_from=forecast_train_from,
            training_to=forecast_train_to,
            forecast_from=forecast_from,
            forecast_to=forecast_to,
            confidence_level=self._default_confidence_level,
            generated_at=now,
            clamp_min=Decimal("0"),
        )

    def _bootstrap_model(self, model_key: str) -> ForecastModelDefinition:
        now = datetime.now(timezone.utc)
        active = ForecastModelDefinition(
            id=new_uuid(),
            model_key=model_key,
            model_family=self._default_model_family,
            training_window_days=90,
            minimum_history_days=self._series_definition.minimum_history_days,
            status=ForecastModelStatus.ACTIVE,
            version=1,
            created_at=now,
            approved_at=now,
        )
        self._model_repository.save(active)
        return active
