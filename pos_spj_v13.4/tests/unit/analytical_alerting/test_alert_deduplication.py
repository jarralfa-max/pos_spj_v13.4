from datetime import datetime, timedelta, timezone

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.services.alert_deduplication import should_suppress
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.shared.ids import new_uuid

_BASE = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _alert(created_at, fingerprint="STOCKOUT_RISK:b1:p1") -> AnalyticalAlert:
    return AnalyticalAlert(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=AlertSeverity.HIGH, title="t", message="m", branch_id="b1", target_id="p1",
        evidence={"x": "1"}, fingerprint=fingerprint, status=AlertStatus.OPEN,
        created_at=created_at,
    )


def test_suppresses_within_cooldown_window():
    existing = (_alert(_BASE),)
    now = _BASE + timedelta(minutes=30)
    assert should_suppress(existing, "STOCKOUT_RISK:b1:p1", cooldown_minutes=60, now=now) is True


def test_does_not_suppress_after_cooldown_expires():
    existing = (_alert(_BASE),)
    now = _BASE + timedelta(minutes=90)
    assert should_suppress(existing, "STOCKOUT_RISK:b1:p1", cooldown_minutes=60, now=now) is False


def test_does_not_suppress_different_fingerprint():
    existing = (_alert(_BASE, fingerprint="OVERSTOCK:b1:p1"),)
    now = _BASE + timedelta(minutes=1)
    assert should_suppress(existing, "STOCKOUT_RISK:b1:p1", cooldown_minutes=60, now=now) is False


def test_zero_cooldown_never_suppresses():
    existing = (_alert(_BASE),)
    now = _BASE
    assert should_suppress(existing, "STOCKOUT_RISK:b1:p1", cooldown_minutes=0, now=now) is False


def test_no_existing_alerts_never_suppresses():
    assert should_suppress((), "STOCKOUT_RISK:b1:p1", cooldown_minutes=60, now=_BASE) is False
