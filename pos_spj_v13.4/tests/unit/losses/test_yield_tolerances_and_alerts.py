from decimal import Decimal

from backend.application.losses.production_loss import ProductionYieldCalculator


def test_explicit_profile_band_overrides_symmetric_version_tolerance():
    analysis = ProductionYieldCalculator().calculate(
        input_weight=Decimal("100"), actual_output_weight=Decimal("86"),
        expected_yield_pct=Decimal("90"), tolerance_pct=Decimal("1"),
        minimum_yield_pct=Decimal("85"), maximum_yield_pct=Decimal("93"))
    assert analysis.lower_tolerance_pct == Decimal("85")
    assert analysis.upper_tolerance_pct == Decimal("93")
    assert analysis.severity == "NORMAL"
    assert analysis.variance_pct == Decimal("-4.00")


def test_low_yield_raises_out_of_tolerance_alert_severity():
    analysis = ProductionYieldCalculator().calculate(
        input_weight=Decimal("100"), actual_output_weight=Decimal("84"),
        expected_yield_pct=Decimal("90"), tolerance_pct=Decimal("2"))
    assert analysis.severity == "OUT_OF_TOLERANCE"
    assert analysis.is_abnormal


def test_zero_real_yield_is_critical():
    analysis = ProductionYieldCalculator().calculate(
        input_weight=Decimal("100"), actual_output_weight=Decimal("0"),
        expected_yield_pct=Decimal("90"), tolerance_pct=Decimal("2"))
    assert analysis.actual_yield_pct == Decimal("0.00")
    assert analysis.severity == "CRITICAL"


def test_above_upper_band_is_warning_without_fabricating_loss():
    analysis = ProductionYieldCalculator().calculate(
        input_weight=Decimal("100"), actual_output_weight=Decimal("96"),
        expected_yield_pct=Decimal("90"), tolerance_pct=Decimal("2"))
    assert analysis.severity == "WARNING"
    assert analysis.abnormal_loss_weight == Decimal("0")
