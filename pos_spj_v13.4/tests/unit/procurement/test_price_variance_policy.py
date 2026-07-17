"""PUR-13 step 1b — PriceVariancePolicy (migrated cost-variance alert, Decimal)."""

from decimal import Decimal

import pytest

from backend.domain.procurement.exceptions import ProcurementDomainError
from backend.domain.procurement.pricing_policies import (
    PriceDirection,
    PriceVariancePolicy,
)


def test_significant_increase():
    r = PriceVariancePolicy().evaluate("100", "125")  # +25% ≥ 20%
    assert r.direction is PriceDirection.UP
    assert r.percent == Decimal("25")
    assert r.is_significant is True
    assert r.label() == "▲ SUBIÓ 25.0%"


def test_significant_decrease():
    r = PriceVariancePolicy().evaluate("100", "70")  # -30%
    assert r.direction is PriceDirection.DOWN
    assert r.is_significant is True
    assert r.label() == "▼ BAJÓ 30.0%"


def test_within_threshold_is_not_significant():
    r = PriceVariancePolicy().evaluate("100", "110")  # +10% < 20%
    assert r.is_significant is False


def test_threshold_is_configurable():
    r = PriceVariancePolicy(threshold_percent="5").evaluate("100", "110")
    assert r.is_significant is True


def test_no_baseline_is_flat():
    r = PriceVariancePolicy().evaluate("0", "50")
    assert r.direction is PriceDirection.FLAT and r.is_significant is False
    assert r.label() == "—"


def test_rejects_float():
    with pytest.raises(ProcurementDomainError):
        PriceVariancePolicy().evaluate(100.0, "125")


def test_boundary_exactly_threshold_is_significant():
    r = PriceVariancePolicy().evaluate("100", "120")  # exactly 20%
    assert r.is_significant is True
