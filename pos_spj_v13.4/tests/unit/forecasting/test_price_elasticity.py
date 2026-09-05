from decimal import Decimal

from backend.domain.forecasting.enums import EstimateConfidence
from backend.domain.forecasting.services.price_elasticity import estimate_price_elasticity

# Perfectly log-linear demand curve q = 100/p (elasticity exactly -1):
# ln(q) = ln(100) - ln(p), a perfect line, so OLS recovers slope = -1 exactly
# regardless of how many/which points are used.
_PERFECT_UNIT_ELASTIC_HISTORY = tuple(
    (Decimal(p), Decimal("100") / Decimal(p))
    for p in (1, 2, 4, 5, 8, 10, 20, 25, 40, 50)
)


def test_high_confidence_with_ten_points_recovers_exact_elasticity():
    estimate = estimate_price_elasticity("p1", "b1", _PERFECT_UNIT_ELASTIC_HISTORY, minimum_points=5)
    assert estimate.confidence == EstimateConfidence.HIGH
    assert estimate.elasticity_coefficient == Decimal("-1")
    assert estimate.sample_size == 10


def test_medium_confidence_with_fewer_points_same_exact_elasticity():
    subset = _PERFECT_UNIT_ELASTIC_HISTORY[:7]
    estimate = estimate_price_elasticity("p1", "b1", subset, minimum_points=5)
    assert estimate.confidence == EstimateConfidence.MEDIUM
    assert estimate.elasticity_coefficient == Decimal("-1")


def test_low_confidence_when_too_few_points():
    estimate = estimate_price_elasticity(
        "p1", "b1", _PERFECT_UNIT_ELASTIC_HISTORY[:3], minimum_points=5)
    assert estimate.confidence == EstimateConfidence.LOW
    assert estimate.elasticity_coefficient is None


def test_low_confidence_when_no_price_variation():
    """§35: never invent an elasticity from a flat price history."""
    history = tuple((Decimal("10"), Decimal(q)) for q in (100, 95, 105, 98, 102, 101))
    estimate = estimate_price_elasticity("p1", "b1", history, minimum_points=5)
    assert estimate.confidence == EstimateConfidence.LOW
    assert estimate.elasticity_coefficient is None


def test_ignores_non_positive_price_or_quantity_points():
    history = _PERFECT_UNIT_ELASTIC_HISTORY + ((Decimal("0"), Decimal("50")),
                                                (Decimal("30"), Decimal("0")))
    estimate = estimate_price_elasticity("p1", "b1", history, minimum_points=5)
    assert estimate.sample_size == 10  # the two invalid points are excluded
