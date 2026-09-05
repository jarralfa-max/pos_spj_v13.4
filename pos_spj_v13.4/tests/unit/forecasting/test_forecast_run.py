from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.domain.analytics.enums import ScopePolicy
from backend.domain.forecasting.enums import ForecastRunStatus
from backend.domain.forecasting.value_objects.forecast_run import (
    ForecastResult,
    ForecastResultPoint,
    ForecastRun,
)
from backend.shared.ids import new_uuid


def _make_run(**overrides) -> ForecastRun:
    fields = dict(
        run_id=new_uuid(),
        model_version_id=new_uuid(),
        series_definition_key="daily_sales_by_product",
        scope_policy=ScopePolicy.BRANCH,
        scope_value="branch-1",
        training_from=date(2026, 6, 1),
        training_to=date(2026, 8, 31),
        forecast_from=date(2026, 9, 1),
        forecast_to=date(2026, 9, 30),
        horizon_days=30,
        generated_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        confidence_level=Decimal("0.90"),
        status=ForecastRunStatus.COMPLETED,
    )
    fields.update(overrides)
    return ForecastRun(**fields)


def test_valid_forecast_run_constructs():
    run = _make_run()
    assert run.status == ForecastRunStatus.COMPLETED


def test_rejects_training_to_before_training_from():
    with pytest.raises(ValueError):
        _make_run(training_from=date(2026, 8, 31), training_to=date(2026, 6, 1))


def test_rejects_forecast_to_before_forecast_from():
    with pytest.raises(ValueError):
        _make_run(forecast_from=date(2026, 9, 30), forecast_to=date(2026, 9, 1))


def test_rejects_non_positive_horizon():
    with pytest.raises(ValueError):
        _make_run(horizon_days=0)


@pytest.mark.parametrize("level", [Decimal("0"), Decimal("-0.1"), Decimal("1.01")])
def test_rejects_confidence_level_outside_0_1(level):
    with pytest.raises(ValueError):
        _make_run(confidence_level=level)


def test_confidence_level_of_exactly_one_is_allowed():
    run = _make_run(confidence_level=Decimal("1"))
    assert run.confidence_level == Decimal("1")


def test_rejects_non_uuidv7_run_id():
    with pytest.raises(ValueError):
        _make_run(run_id="not-a-uuid")


def _point(ts=date(2026, 9, 1), point=Decimal("100"), lower=Decimal("80"),
           upper=Decimal("120")) -> ForecastResultPoint:
    return ForecastResultPoint(timestamp=ts, point_forecast=point,
                                lower_bound=lower, upper_bound=upper)


def test_valid_result_point_constructs():
    point = _point()
    assert point.lower_bound <= point.point_forecast <= point.upper_bound


def test_result_point_rejects_inverted_bounds():
    """§25: never present a forecast as certainty — bounds must bracket the
    point estimate."""
    with pytest.raises(ValueError):
        _point(lower=Decimal("150"), upper=Decimal("120"))


def test_result_point_rejects_point_outside_bounds():
    with pytest.raises(ValueError):
        _point(point=Decimal("200"), lower=Decimal("80"), upper=Decimal("120"))


def test_forecast_result_requires_sorted_points():
    run_id = new_uuid()
    ordered = (
        _point(ts=date(2026, 9, 1)),
        _point(ts=date(2026, 9, 2)),
    )
    result = ForecastResult(run_id=run_id, points=ordered)
    assert len(result.points) == 2

    unordered = (
        _point(ts=date(2026, 9, 2)),
        _point(ts=date(2026, 9, 1)),
    )
    with pytest.raises(ValueError):
        ForecastResult(run_id=run_id, points=unordered)


def test_forecast_result_rejects_empty_points():
    with pytest.raises(ValueError):
        ForecastResult(run_id=new_uuid(), points=())
