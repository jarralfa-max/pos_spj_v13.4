"""ScaleStabilityPolicy — SET-9 (§22): does this run of readings add up
to a trustworthy weight? A scale reporting its own "stable" flag isn't
enough on its own (a jittery scale can flicker stable/unstable) — this
requires the trailing `required_stable_readings` readings to *all* be
flagged stable *and* agree with each other within `tolerance` before
handing back a confirmed value. Pure function: no gateway, no I/O — the
caller (a future scale gateway/use case) feeds it the reading history.
"""

from __future__ import annotations

from backend.domain.device_management.value_objects.stability_policy import StabilityPolicy
from backend.domain.device_management.value_objects.weight_reading import WeightReading


def evaluate_stability(readings: list[WeightReading], policy: StabilityPolicy) -> WeightReading | None:
    """Return the confirmed stable reading (the most recent one in the
    qualifying window), or None if `readings` doesn't yet satisfy
    `policy`."""
    if len(readings) < policy.required_stable_readings:
        return None

    window = readings[-policy.required_stable_readings:]
    if not all(reading.stable for reading in window):
        return None

    baseline = window[0].value
    if any(abs(reading.value - baseline) > policy.tolerance for reading in window[1:]):
        return None

    return window[-1]
