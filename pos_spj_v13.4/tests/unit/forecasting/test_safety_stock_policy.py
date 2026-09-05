from decimal import Decimal

import pytest

from backend.domain.forecasting.enums import SafetyStockMethod
from backend.domain.forecasting.exceptions import ForecastingDomainError
from backend.domain.forecasting.services import safety_stock_policy as ssp


def test_std_dev_of_known_series():
    # mean=10, deviations [-1,1,-1,1], variance=4/3 (sample, n-1)
    history = (Decimal("9"), Decimal("11"), Decimal("9"), Decimal("11"))
    expected = (Decimal("4") / Decimal("3")).sqrt()
    assert ssp.std_dev(history) == expected


def test_std_dev_requires_at_least_two_points():
    with pytest.raises(ForecastingDomainError):
        ssp.std_dev((Decimal("5"),))


def test_fixed_days_method():
    result = ssp.safety_stock(
        SafetyStockMethod.FIXED_DAYS, avg_daily_demand=Decimal("10"),
        lead_time_days=4, fixed_days=Decimal("3"))
    assert result == Decimal("30")


def test_fixed_days_requires_fixed_days_param():
    with pytest.raises(ValueError):
        ssp.safety_stock(SafetyStockMethod.FIXED_DAYS, avg_daily_demand=Decimal("10"),
                          lead_time_days=4)


def test_service_level_matches_manual_z_times_std_times_sqrt_lead_time():
    history = (Decimal("9"), Decimal("11"), Decimal("9"), Decimal("11"))
    result = ssp.safety_stock(
        SafetyStockMethod.SERVICE_LEVEL, avg_daily_demand=Decimal("10"),
        lead_time_days=4, daily_demand_history=history, service_level=Decimal("0.95"))
    expected = ssp.SERVICE_LEVEL_Z[Decimal("0.95")] * ssp.std_dev(history) * Decimal(4).sqrt()
    assert result == expected


def test_service_level_rejects_unsupported_level():
    with pytest.raises(ValueError):
        ssp.safety_stock(
            SafetyStockMethod.SERVICE_LEVEL, avg_daily_demand=Decimal("10"),
            lead_time_days=4, daily_demand_history=(Decimal("1"), Decimal("2")),
            service_level=Decimal("0.5"))


def test_demand_variability_is_at_least_service_level_when_lead_time_varies():
    """Adding lead-time variance on top of demand variance can only widen
    the safety stock relative to the SERVICE_LEVEL method with the same
    demand history and zero lead-time variance is the SERVICE_LEVEL floor
    with an extra sqrt(lead_time) factor difference — check the >0 term adds."""
    history = (Decimal("9"), Decimal("11"), Decimal("9"), Decimal("11"))
    no_lt_variance = ssp.safety_stock(
        SafetyStockMethod.DEMAND_VARIABILITY, avg_daily_demand=Decimal("10"),
        lead_time_days=4, daily_demand_history=history, service_level=Decimal("0.95"),
        lead_time_std_dev_days=Decimal("0"))
    with_lt_variance = ssp.safety_stock(
        SafetyStockMethod.DEMAND_VARIABILITY, avg_daily_demand=Decimal("10"),
        lead_time_days=4, daily_demand_history=history, service_level=Decimal("0.95"),
        lead_time_std_dev_days=Decimal("1"))
    assert with_lt_variance > no_lt_variance


def test_custom_method_returns_supplied_value():
    result = ssp.safety_stock(
        SafetyStockMethod.CUSTOM, avg_daily_demand=Decimal("10"), lead_time_days=4,
        custom_value=Decimal("42"))
    assert result == Decimal("42")


def test_custom_method_requires_non_negative_value():
    with pytest.raises(ValueError):
        ssp.safety_stock(SafetyStockMethod.CUSTOM, avg_daily_demand=Decimal("10"),
                          lead_time_days=4, custom_value=Decimal("-1"))


def test_reorder_point():
    result = ssp.reorder_point(Decimal("10"), 4, Decimal("15"))
    assert result == Decimal("55")


def test_recommended_quantity_never_negative():
    # target below current stock -> 0, never a negative "un-order"
    result = ssp.recommended_quantity(
        current_stock=Decimal("1000"), reorder_point_qty=Decimal("50"),
        target_coverage_days=Decimal("7"), avg_daily_demand=Decimal("10"))
    assert result == Decimal("0")


def test_recommended_quantity_positive_case():
    result = ssp.recommended_quantity(
        current_stock=Decimal("20"), reorder_point_qty=Decimal("50"),
        target_coverage_days=Decimal("7"), avg_daily_demand=Decimal("10"))
    # target = 50 + 70 = 120; 120 - 20 = 100
    assert result == Decimal("100")


def test_days_coverage_none_when_no_demand():
    assert ssp.days_coverage(Decimal("100"), Decimal("0")) is None


def test_days_coverage_zero_when_no_stock():
    assert ssp.days_coverage(Decimal("0"), Decimal("10")) == Decimal("0")


def test_days_coverage_division():
    assert ssp.days_coverage(Decimal("50"), Decimal("10")) == Decimal("5")


@pytest.mark.parametrize("days_cov,expected", [
    (None, "NONE"), (Decimal("0"), "CRITICAL"), (Decimal("2"), "HIGH"),
    (Decimal("5"), "MEDIUM"), (Decimal("30"), "LOW"),
])
def test_urgency_level(days_cov, expected):
    assert ssp.urgency_level(days_cov) == expected
