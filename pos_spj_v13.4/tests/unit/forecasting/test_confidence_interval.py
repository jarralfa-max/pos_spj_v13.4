from decimal import Decimal

import pytest

from backend.domain.forecasting.services.confidence_interval import build_bounds


def test_build_bounds_symmetric_around_point_forecast():
    bounds = build_bounds((Decimal("100"),), rmse=Decimal("10"), confidence_level=Decimal("0.90"))
    lower, upper = bounds[0]
    midpoint = (lower + upper) / 2
    assert midpoint == Decimal("100")
    assert lower < Decimal("100") < upper


def test_wider_rmse_yields_wider_interval():
    narrow = build_bounds((Decimal("100"),), rmse=Decimal("5"), confidence_level=Decimal("0.90"))
    wide = build_bounds((Decimal("100"),), rmse=Decimal("20"), confidence_level=Decimal("0.90"))
    narrow_width = narrow[0][1] - narrow[0][0]
    wide_width = wide[0][1] - wide[0][0]
    assert wide_width > narrow_width


def test_higher_confidence_level_yields_wider_interval():
    lower_conf = build_bounds((Decimal("100"),), rmse=Decimal("10"), confidence_level=Decimal("0.80"))
    higher_conf = build_bounds((Decimal("100"),), rmse=Decimal("10"), confidence_level=Decimal("0.99"))
    lower_width = lower_conf[0][1] - lower_conf[0][0]
    higher_width = higher_conf[0][1] - higher_conf[0][0]
    assert higher_width > lower_width


def test_rejects_unsupported_confidence_level():
    with pytest.raises(ValueError):
        build_bounds((Decimal("100"),), rmse=Decimal("10"), confidence_level=Decimal("0.5"))


def test_rejects_negative_rmse():
    with pytest.raises(ValueError):
        build_bounds((Decimal("100"),), rmse=Decimal("-1"), confidence_level=Decimal("0.90"))


def test_clamp_min_floors_lower_bound():
    bounds = build_bounds(
        (Decimal("2"),), rmse=Decimal("10"), confidence_level=Decimal("0.90"),
        clamp_min=Decimal("0"),
    )
    lower, upper = bounds[0]
    assert lower == Decimal("0")
    assert upper > Decimal("0")


def test_returns_one_pair_per_point_forecast_in_order():
    bounds = build_bounds(
        (Decimal("10"), Decimal("20"), Decimal("30")),
        rmse=Decimal("1"), confidence_level=Decimal("0.90"),
    )
    assert len(bounds) == 3
    assert bounds[0][0] < Decimal("10") < bounds[0][1]
    assert bounds[2][0] < Decimal("30") < bounds[2][1]
