"""AnalyticalNotificationSubscription (§55, BI-21).

Opt-in, not opt-out: a resolved recipient (§118 — permission/role/scope
based) only actually gets notified if they hold a subscription for that
exact `alert_type`, at or above their `minimum_severity`, on their chosen
`channel`, outside their `quiet_hours` — see
`services/notification_gating.py::should_notify`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertType
from backend.domain.notifications.enums import NotificationChannel
from backend.shared.ids import validate_uuidv7

#: A subscription with this branch_scope applies to every branch the
#: recipient is otherwise eligible for (mirrors `DemandPlanningService`'s
#: own `"ALL_BRANCHES"` sentinel, BI-12 — same vocabulary, not a new one).
ALL_BRANCHES = "ALL_BRANCHES"


@dataclass(frozen=True, slots=True)
class AnalyticalNotificationSubscription:
    id: str
    user_id: str
    alert_type: AlertType
    minimum_severity: AlertSeverity
    channel: NotificationChannel
    branch_scope: str
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        if not self.user_id:
            raise ValueError("AnalyticalNotificationSubscription.user_id is required")
        if not self.branch_scope:
            raise ValueError("AnalyticalNotificationSubscription.branch_scope is required")
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet_hours_start and quiet_hours_end must be set together")
