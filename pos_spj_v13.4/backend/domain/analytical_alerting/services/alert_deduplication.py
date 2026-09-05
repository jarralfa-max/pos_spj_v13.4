"""Alert deduplication / cooldown (§49, BI-20) — "evitar alertas
repetitivas": don't fire the same fingerprint again within its cooldown
window, regardless of whether the earlier one was already resolved.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert


def should_suppress(
    existing_alerts: tuple[AnalyticalAlert, ...],
    fingerprint: str,
    cooldown_minutes: int,
    now: datetime,
) -> bool:
    if cooldown_minutes <= 0:
        return False
    cutoff = now - timedelta(minutes=cooldown_minutes)
    return any(
        alert.fingerprint == fingerprint and alert.created_at >= cutoff
        for alert in existing_alerts
    )
