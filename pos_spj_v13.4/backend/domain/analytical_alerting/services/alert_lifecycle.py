"""Alert lifecycle transitions (§50, BI-20) — same immutable-replace
discipline as `decision_intelligence.recommendation_transitions` (BI-18):
every function returns a new `AnalyticalAlert`, never mutates in place.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

from backend.domain.analytical_alerting.enums import AlertStatus
from backend.domain.analytical_alerting.exceptions import InvalidAlertTransitionError
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert

_ALLOWED_TRANSITIONS: dict[AlertStatus, frozenset[AlertStatus]] = {
    AlertStatus.OPEN: frozenset({
        AlertStatus.ACKNOWLEDGED, AlertStatus.DISMISSED, AlertStatus.EXPIRED,
    }),
    AlertStatus.ACKNOWLEDGED: frozenset({
        AlertStatus.IN_PROGRESS, AlertStatus.DISMISSED, AlertStatus.EXPIRED,
    }),
    AlertStatus.IN_PROGRESS: frozenset({
        AlertStatus.RESOLVED, AlertStatus.DISMISSED, AlertStatus.EXPIRED,
    }),
    AlertStatus.RESOLVED: frozenset(),
    AlertStatus.DISMISSED: frozenset(),
    AlertStatus.EXPIRED: frozenset(),
}


def _transition(alert: AnalyticalAlert, new_status: AlertStatus, **changes) -> AnalyticalAlert:
    allowed = _ALLOWED_TRANSITIONS.get(alert.status, frozenset())
    if new_status not in allowed:
        raise InvalidAlertTransitionError(
            f"Cannot transition AnalyticalAlert from {alert.status} to {new_status}"
        )
    return dataclasses.replace(alert, status=new_status, **changes)


def acknowledge(alert: AnalyticalAlert, actor_id: str, at: datetime) -> AnalyticalAlert:
    if not actor_id:
        raise ValueError("acknowledge requires actor_id")
    return _transition(alert, AlertStatus.ACKNOWLEDGED, acknowledged_by=actor_id, acknowledged_at=at)


def start_progress(alert: AnalyticalAlert) -> AnalyticalAlert:
    return _transition(alert, AlertStatus.IN_PROGRESS)


def resolve(alert: AnalyticalAlert, actor_id: str, at: datetime, reason: str) -> AnalyticalAlert:
    if not actor_id:
        raise ValueError("resolve requires actor_id")
    if not reason:
        raise ValueError("resolve requires a reason (§50)")
    return _transition(alert, AlertStatus.RESOLVED, resolved_by=actor_id, resolved_at=at, reason=reason)


def dismiss(alert: AnalyticalAlert, actor_id: str, at: datetime, reason: str) -> AnalyticalAlert:
    if not actor_id:
        raise ValueError("dismiss requires actor_id")
    if not reason:
        raise ValueError("dismiss requires a reason (§50)")
    return _transition(alert, AlertStatus.DISMISSED, resolved_by=actor_id, resolved_at=at, reason=reason)


def expire(alert: AnalyticalAlert) -> AnalyticalAlert:
    """No actor/reason — an expiry is a scheduler noticing `valid_until`
    passed, not a human decision, so there's nothing to attribute it to."""
    return _transition(alert, AlertStatus.EXPIRED)
