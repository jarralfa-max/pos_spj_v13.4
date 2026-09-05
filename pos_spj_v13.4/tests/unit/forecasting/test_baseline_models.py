from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.domain.forecasting.exceptions import InsufficientHistoryError
from backend.domain.forecasting.services import baseline_models as bm
from backend.domain.forecasting.value_objects.time_series import TimeSeriesObservation


def _series(values: list[int | str]) -> tuple[TimeSeriesObservation, ...]:
    start = date(2026, 8, 1)
    return tuple(
        TimeSeriesObservation(timestamp=start + timedelta(days=i), value=Decimal(str(v)))
        for i, v in enumerate(values)
    )


def test_naive_repeats_last_value():
    obs = _series([10, 20, 30])
    assert bm.naive(obs, horizon_days=3) == (Decimal("30"), Decimal("30"), Decimal("30"))


def test_naive_requires_at_least_one_observation():
    with pytest.raises(InsufficientHistoryError):
        bm.naive((), horizon_days=1)


def test_naive_rejects_non_positive_horizon():
    with pytest.raises(ValueError):
        bm.naive(_series([1]), horizon_days=0)


def test_seasonal_naive_cycles_last_season():
    obs = _series([1, 2, 3, 4, 5, 6])
    result = bm.seasonal_naive(obs, horizon_days=5, season_length=3)
    assert result == (Decimal("4"), Decimal("5"), Decimal("6"), Decimal("4"), Decimal("5"))


def test_seasonal_naive_requires_full_season_of_history():
    obs = _series([1, 2])
    with pytest.raises(InsufficientHistoryError):
        bm.seasonal_naive(obs, horizon_days=1, season_length=3)


def test_moving_average_flat_forecast():
    obs = _series([1, 2, 3, 4, 5, 6])
    result = bm.moving_average(obs, horizon_days=2, window=3)
    assert result == (Decimal("5"), Decimal("5"))


def test_moving_average_requires_full_window():
    obs = _series([1, 2])
    with pytest.raises(InsufficientHistoryError):
        bm.moving_average(obs, horizon_days=1, window=3)


def test_weighted_moving_average_favors_recent_values():
    obs = _series([0, 0, 0, 3, 6, 9])
    result = bm.weighted_moving_average(obs, horizon_days=1, window=3)
    # weights 1,2,3 over [3,6,9]: (3*1+6*2+9*3)/6 = 42/6 = 7
    assert result == (Decimal("7"),)


def test_ses_smooths_toward_recent_value():
    obs = _series([10, 20])
    result = bm.simple_exponential_smoothing(obs, horizon_days=2, alpha=Decimal("0.5"))
    assert result == (Decimal("15"), Decimal("15"))


def test_ses_rejects_alpha_out_of_range():
    with pytest.raises(ValueError):
        bm.simple_exponential_smoothing(_series([1, 2]), horizon_days=1, alpha=Decimal("0"))
    with pytest.raises(ValueError):
        bm.simple_exponential_smoothing(_series([1, 2]), horizon_days=1, alpha=Decimal("1.5"))


def test_holt_extrapolates_linear_trend():
    obs = _series([10, 20, 30])
    result = bm.holt(obs, horizon_days=2, alpha=Decimal("0.5"), beta=Decimal("0.5"))
    assert result == (Decimal("40"), Decimal("50"))


def test_holt_requires_at_least_two_observations():
    with pytest.raises(InsufficientHistoryError):
        bm.holt(_series([1]), horizon_days=1)


def test_holt_winters_reproduces_perfectly_periodic_pattern():
    """With a perfectly periodic, trend-free pattern, Holt-Winters must
    reconstruct the exact pattern regardless of alpha/beta/gamma — the
    updates are a fixed point (each step's error is zero)."""
    obs = _series([10, 20, 10, 20] * 3)  # 3 full seasons, season_length=4
    result = bm.holt_winters(
        obs, horizon_days=4, season_length=4,
        alpha=Decimal("0.3"), beta=Decimal("0.2"), gamma=Decimal("0.4"),
    )
    assert result == (Decimal("10"), Decimal("20"), Decimal("10"), Decimal("20"))


def test_holt_winters_requires_two_full_seasons():
    obs = _series([10, 20, 10, 20])  # only 1 season
    with pytest.raises(InsufficientHistoryError):
        bm.holt_winters(obs, horizon_days=1, season_length=4)


def test_holt_winters_rejects_season_length_of_one():
    obs = _series([1] * 10)
    with pytest.raises(ValueError):
        bm.holt_winters(obs, horizon_days=1, season_length=1)
