from datetime import datetime, time, timezone

import pytest

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.domain.analytical_alerting.services.notification_gating import (
    is_within_quiet_hours,
    severity_meets_minimum,
    should_notify,
)
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.analytical_alerting.value_objects.notification_subscription import (
    ALL_BRANCHES,
    AnalyticalNotificationSubscription,
)
from backend.domain.notifications.enums import NotificationChannel
from backend.shared.ids import new_uuid


@pytest.mark.parametrize("severity,minimum,expected", [
    (AlertSeverity.CRITICAL, AlertSeverity.HIGH, True),
    (AlertSeverity.HIGH, AlertSeverity.HIGH, True),
    (AlertSeverity.MEDIUM, AlertSeverity.HIGH, False),
    (AlertSeverity.INFO, AlertSeverity.LOW, False),
])
def test_severity_meets_minimum(severity, minimum, expected):
    assert severity_meets_minimum(severity, minimum) is expected


def test_is_within_quiet_hours_same_day_window():
    assert is_within_quiet_hours(time(14, 0), time(9, 0), time(18, 0)) is True
    assert is_within_quiet_hours(time(8, 0), time(9, 0), time(18, 0)) is False


def test_is_within_quiet_hours_overnight_window():
    # 22:00 - 06:00 wraps past midnight
    assert is_within_quiet_hours(time(23, 0), time(22, 0), time(6, 0)) is True
    assert is_within_quiet_hours(time(3, 0), time(22, 0), time(6, 0)) is True
    assert is_within_quiet_hours(time(12, 0), time(22, 0), time(6, 0)) is False


def _alert(branch_id="b1", severity=AlertSeverity.HIGH) -> AnalyticalAlert:
    return AnalyticalAlert(
        id=new_uuid(), rule_id=new_uuid(), alert_type=AlertType.STOCKOUT_RISK,
        severity=severity, title="t", message="m", branch_id=branch_id, target_id="p1",
        evidence={"x": "1"}, fingerprint=f"STOCKOUT_RISK:{branch_id}:p1", status=AlertStatus.OPEN,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )


def _subscription(**overrides) -> AnalyticalNotificationSubscription:
    fields = dict(
        id=new_uuid(), user_id="user1", alert_type=AlertType.STOCKOUT_RISK,
        minimum_severity=AlertSeverity.MEDIUM, channel=NotificationChannel.IN_APP,
        branch_scope=ALL_BRANCHES,
    )
    fields.update(overrides)
    return AnalyticalNotificationSubscription(**fields)


def test_should_notify_happy_path():
    assert should_notify(_subscription(), _alert(), time(10, 0)) is True


def test_should_notify_false_when_disabled():
    assert should_notify(_subscription(enabled=False), _alert(), time(10, 0)) is False


def test_should_notify_false_when_alert_type_mismatch():
    assert should_notify(_subscription(alert_type=AlertType.OVERSTOCK), _alert(), time(10, 0)) is False


def test_should_notify_false_when_severity_below_minimum():
    assert should_notify(
        _subscription(minimum_severity=AlertSeverity.CRITICAL), _alert(severity=AlertSeverity.HIGH),
        time(10, 0),
    ) is False


def test_should_notify_false_when_branch_scope_mismatch():
    assert should_notify(
        _subscription(branch_scope="b2"), _alert(branch_id="b1"), time(10, 0),
    ) is False


def test_should_notify_true_when_branch_scope_matches_exactly():
    assert should_notify(
        _subscription(branch_scope="b1"), _alert(branch_id="b1"), time(10, 0),
    ) is True


def test_should_notify_false_during_quiet_hours():
    sub = _subscription(quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0))
    assert should_notify(sub, _alert(), time(23, 0)) is False
    assert should_notify(sub, _alert(), time(10, 0)) is True
