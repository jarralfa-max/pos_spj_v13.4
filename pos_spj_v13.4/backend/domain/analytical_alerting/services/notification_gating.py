"""Notification gating (§55, BI-21) — decides whether a resolved candidate
recipient actually gets notified for a given alert: matching alert type,
severity at or above their configured minimum, matching branch scope, and
outside their quiet hours. Opt-in: no subscription means no notification,
even if the recipient was a valid candidate (§118 resolves *candidates*;
this decides who among them actually wants to hear about it, and when).
"""

from __future__ import annotations

from datetime import time

from backend.domain.analytical_alerting.enums import AlertSeverity
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.analytical_alerting.value_objects.notification_subscription import (
    ALL_BRANCHES,
    AnalyticalNotificationSubscription,
)

_SEVERITY_ORDER: dict[AlertSeverity, int] = {
    AlertSeverity.INFO: 0,
    AlertSeverity.LOW: 1,
    AlertSeverity.MEDIUM: 2,
    AlertSeverity.HIGH: 3,
    AlertSeverity.CRITICAL: 4,
}


def severity_meets_minimum(severity: AlertSeverity, minimum: AlertSeverity) -> bool:
    return _SEVERITY_ORDER[severity] >= _SEVERITY_ORDER[minimum]


def is_within_quiet_hours(now_time: time, start: time, end: time) -> bool:
    """Handles a window that wraps past midnight (e.g. 22:00-06:00)."""
    if start <= end:
        return start <= now_time < end
    return now_time >= start or now_time < end


def should_notify(
    subscription: AnalyticalNotificationSubscription,
    alert: AnalyticalAlert,
    now_time: time,
) -> bool:
    if not subscription.enabled:
        return False
    if subscription.alert_type != alert.alert_type:
        return False
    if not severity_meets_minimum(alert.severity, subscription.minimum_severity):
        return False
    if subscription.branch_scope != ALL_BRANCHES and subscription.branch_scope != alert.branch_id:
        return False
    if subscription.quiet_hours_start is not None and subscription.quiet_hours_end is not None:
        if is_within_quiet_hours(now_time, subscription.quiet_hours_start,
                                  subscription.quiet_hours_end):
            return False
    return True
