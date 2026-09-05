from datetime import date, timedelta
from decimal import Decimal

from backend.application.forecasting.services.demand_planning_service import (
    DemandPlanningService,
)
from backend.application.forecasting.services.time_series_dataset_builder import (
    TimeSeriesDatasetBuilder,
)
from backend.domain.analytics.enums import ScopePolicy, TimeGrain
from backend.domain.forecasting.enums import ForecastModelFamily, ForecastRunStatus
from backend.domain.forecasting.value_objects.time_series import (
    TimeSeriesDefinition,
    TimeSeriesObservation,
)


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


class _FakeModelRepository:
    def __init__(self):
        self.saved = []
        self._by_key = {}

    def save(self, definition):
        self.saved.append(definition)
        self._by_key[definition.model_key] = definition

    def get(self, model_key, version):
        raise NotImplementedError

    def get_active(self, model_key):
        model = self._by_key.get(model_key)
        return model if model is not None and model.status.value == "ACTIVE" else None

    def list_versions(self, model_key):
        raise NotImplementedError


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
        key="daily_sales_by_product", name="X", dimension_keys=("product", "branch"),
        time_grain=TimeGrain.DAILY, value_unit="unidades", minimum_history_days=14,
    )


def test_forecast_bootstraps_a_model_on_first_call():
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("7")))
    model_repo = _FakeModelRepository()
    run_repo = _FakeRunRepository()
    service = DemandPlanningService(builder, model_repo, run_repo, _series_definition())

    run, result = service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=3, as_of=date(2026, 12, 1))

    assert run.status == ForecastRunStatus.COMPLETED
    assert len(result.points) == 3
    assert model_repo.saved  # bootstrap happened
    assert run_repo.saved


def test_constant_series_forecast_has_zero_width_confidence_interval():
    """A perfectly constant series has zero backtest error, so the interval
    collapses to the point forecast."""
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("7")))
    model_repo = _FakeModelRepository()
    run_repo = _FakeRunRepository()
    service = DemandPlanningService(builder, model_repo, run_repo, _series_definition())

    _, result = service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=2, as_of=date(2026, 12, 1))

    for point in result.points:
        assert point.point_forecast == Decimal("7")
        assert point.lower_bound == Decimal("7")
        assert point.upper_bound == Decimal("7")


def test_second_call_reuses_the_bootstrapped_active_model():
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("7")))
    model_repo = _FakeModelRepository()
    run_repo = _FakeRunRepository()
    service = DemandPlanningService(builder, model_repo, run_repo, _series_definition())

    service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=2, as_of=date(2026, 12, 1))
    first_bootstrap_count = len(model_repo.saved)
    service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=2, as_of=date(2026, 12, 2))

    assert len(model_repo.saved) == first_bootstrap_count  # no second bootstrap


def test_no_branch_scopes_to_company():
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("5")))
    model_repo = _FakeModelRepository()
    run_repo = _FakeRunRepository()
    service = DemandPlanningService(builder, model_repo, run_repo, _series_definition())

    run, _ = service.forecast_product_demand(
        product_id="p1", branch_id=None, horizon_days=1, as_of=date(2026, 12, 1))

    assert run.scope_policy == ScopePolicy.COMPANY
    assert run.scope_value == "ALL_BRANCHES"


def test_forecast_horizon_and_dates_line_up_with_as_of():
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("5")))
    model_repo = _FakeModelRepository()
    run_repo = _FakeRunRepository()
    service = DemandPlanningService(builder, model_repo, run_repo, _series_definition())

    as_of = date(2026, 12, 1)
    run, result = service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=5, as_of=as_of)

    assert run.forecast_from == as_of
    assert run.forecast_to == as_of + timedelta(days=4)
    assert run.horizon_days == 5
    assert [p.timestamp for p in result.points] == [as_of + timedelta(days=i) for i in range(5)]


def test_ses_family_used_by_default_when_not_overridden():
    builder = TimeSeriesDatasetBuilder(_ConstantReader(Decimal("5")))
    model_repo = _FakeModelRepository()
    run_repo = _FakeRunRepository()
    service = DemandPlanningService(builder, model_repo, run_repo, _series_definition())

    service.forecast_product_demand(
        product_id="p1", branch_id="b1", horizon_days=1, as_of=date(2026, 12, 1))

    assert model_repo.saved[0].model_family == ForecastModelFamily.SES
