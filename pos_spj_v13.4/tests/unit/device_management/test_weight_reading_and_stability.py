"""SET-9 — WeightReading + StabilityPolicy + evaluate_stability
(§22 "estabilidad"). Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.device_management.enums import WeightUnit
from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.domain.device_management.policies.scale_stability_policy import evaluate_stability
from backend.domain.device_management.value_objects.stability_policy import StabilityPolicy
from backend.domain.device_management.value_objects.weight_reading import WeightReading

_NOW = datetime.now(timezone.utc)


def _reading(value: str, stable: bool, offset_ms: int = 0) -> WeightReading:
    return WeightReading.create(
        value=Decimal(value), unit=WeightUnit.KG, stable=stable, at=_NOW + timedelta(milliseconds=offset_ms),
    )


class TestWeightReadingCreate:
    def test_rejects_float(self):
        with pytest.raises(DeviceInvalidValueError):
            WeightReading.create(value=1.5, unit=WeightUnit.KG, stable=True)

    def test_rejects_negative(self):
        with pytest.raises(DeviceInvalidValueError):
            WeightReading.create(value=Decimal("-0.5"), unit=WeightUnit.KG, stable=True)

    def test_accepts_zero(self):
        reading = WeightReading.create(value=Decimal("0"), unit=WeightUnit.KG, stable=True, at=_NOW)
        assert reading.value == Decimal("0")

    def test_records_timestamp_and_stability_flag(self):
        reading = WeightReading.create(value=Decimal("1.5"), unit=WeightUnit.G, stable=False, at=_NOW)
        assert reading.stable is False
        assert reading.unit is WeightUnit.G
        assert reading.read_at == _NOW.isoformat(timespec="seconds")


class TestStabilityPolicyCreate:
    def test_rejects_non_positive_required_readings(self):
        with pytest.raises(DeviceInvalidValueError):
            StabilityPolicy.create(required_stable_readings=0)

    def test_rejects_float_tolerance(self):
        with pytest.raises(DeviceInvalidValueError):
            StabilityPolicy.create(tolerance=0.005)

    def test_rejects_negative_max_wait(self):
        with pytest.raises(DeviceInvalidValueError):
            StabilityPolicy.create(max_wait_seconds=Decimal("-1"))

    def test_defaults_are_sensible(self):
        policy = StabilityPolicy()
        assert policy.required_stable_readings == 2
        assert policy.tolerance == Decimal("0.005")


class TestEvaluateStability:
    def test_confirms_when_enough_matching_stable_readings(self):
        policy = StabilityPolicy.create(required_stable_readings=2, tolerance=Decimal("0.005"))
        readings = [
            _reading("1.230", stable=False),
            _reading("1.502", stable=True, offset_ms=200),
            _reading("1.503", stable=True, offset_ms=400),
        ]
        confirmed = evaluate_stability(readings, policy)
        assert confirmed is not None
        assert confirmed.value == Decimal("1.503")

    def test_returns_none_with_too_few_readings(self):
        policy = StabilityPolicy.create(required_stable_readings=3)
        readings = [_reading("1.5", stable=True), _reading("1.5", stable=True, offset_ms=200)]
        assert evaluate_stability(readings, policy) is None

    def test_returns_none_if_any_reading_in_window_is_unstable(self):
        policy = StabilityPolicy.create(required_stable_readings=2)
        readings = [_reading("1.5", stable=True), _reading("1.5", stable=False, offset_ms=200)]
        assert evaluate_stability(readings, policy) is None

    def test_returns_none_when_readings_disagree_beyond_tolerance(self):
        # "doble lectura" anti-jitter: two readings can both claim
        # "stable" and still be rejected if they don't actually agree.
        policy = StabilityPolicy.create(required_stable_readings=2, tolerance=Decimal("0.005"))
        readings = [_reading("1.230", stable=True), _reading("1.800", stable=True, offset_ms=200)]
        assert evaluate_stability(readings, policy) is None

    def test_accepts_readings_within_tolerance_boundary(self):
        policy = StabilityPolicy.create(required_stable_readings=2, tolerance=Decimal("0.005"))
        readings = [_reading("1.500", stable=True), _reading("1.505", stable=True, offset_ms=200)]
        assert evaluate_stability(readings, policy) is not None

    def test_rejects_readings_just_outside_tolerance_boundary(self):
        policy = StabilityPolicy.create(required_stable_readings=2, tolerance=Decimal("0.005"))
        readings = [_reading("1.500", stable=True), _reading("1.506", stable=True, offset_ms=200)]
        assert evaluate_stability(readings, policy) is None

    def test_only_considers_the_trailing_window(self):
        # An earlier unstable/mismatched reading outside the required
        # window must not block confirmation.
        policy = StabilityPolicy.create(required_stable_readings=2, tolerance=Decimal("0.005"))
        readings = [
            _reading("99.000", stable=False),
            _reading("1.500", stable=True, offset_ms=200),
            _reading("1.503", stable=True, offset_ms=400),
        ]
        confirmed = evaluate_stability(readings, policy)
        assert confirmed is not None
        assert confirmed.value == Decimal("1.503")

    def test_single_required_reading_confirms_immediately_when_stable(self):
        policy = StabilityPolicy.create(required_stable_readings=1)
        readings = [_reading("2.750", stable=True)]
        confirmed = evaluate_stability(readings, policy)
        assert confirmed is not None
        assert confirmed.value == Decimal("2.750")
