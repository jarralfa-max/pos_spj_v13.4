from datetime import time

import pytest

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertType
from backend.domain.analytical_alerting.value_objects.notification_subscription import (
    ALL_BRANCHES,
    AnalyticalNotificationSubscription,
)
from backend.domain.notifications.enums import NotificationChannel
from backend.shared.ids import new_uuid


def _make(**overrides) -> AnalyticalNotificationSubscription:
    fields = dict(
        id=new_uuid(), user_id="user1", alert_type=AlertType.STOCKOUT_RISK,
        minimum_severity=AlertSeverity.MEDIUM, channel=NotificationChannel.IN_APP,
        branch_scope=ALL_BRANCHES,
    )
    fields.update(overrides)
    return AnalyticalNotificationSubscription(**fields)


def test_valid_subscription_constructs():
    sub = _make()
    assert sub.enabled is True


def test_rejects_empty_user_id():
    with pytest.raises(ValueError):
        _make(user_id="")


def test_rejects_empty_branch_scope():
    with pytest.raises(ValueError):
        _make(branch_scope="")


def test_quiet_hours_must_be_set_together():
    with pytest.raises(ValueError):
        _make(quiet_hours_start=time(22, 0), quiet_hours_end=None)
    with pytest.raises(ValueError):
        _make(quiet_hours_start=None, quiet_hours_end=time(6, 0))


def test_quiet_hours_both_set_is_valid():
    sub = _make(quiet_hours_start=time(22, 0), quiet_hours_end=time(6, 0))
    assert sub.quiet_hours_start == time(22, 0)


def test_rejects_non_uuidv7_id():
    with pytest.raises(ValueError):
        _make(id="not-a-uuid")
