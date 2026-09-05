"""AnalyticalAlertEngine (§46-49, BI-20).

Evaluates one `AnalyticalAlertRule` against one already-computed metric
value (from BI-13..17's forecasts/recommendations, or any other analytics
query — this engine doesn't compute metrics itself, only thresholds them)
and creates an `AnalyticalAlert` if the rule is enabled, breached, and not
suppressed by its own cooldown.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.domain.analytical_alerting.enums import AlertStatus
from backend.domain.analytical_alerting.services.alert_deduplication import should_suppress
from backend.domain.analytical_alerting.services.fingerprint import build_fingerprint
from backend.domain.analytical_alerting.value_objects.alert import AnalyticalAlert
from backend.domain.analytical_alerting.value_objects.alert_rule import AnalyticalAlertRule
from backend.shared.ids import new_uuid


class AnalyticalAlertEngine:
    def evaluate(
        self,
        *,
        rule: AnalyticalAlertRule,
        metric_value: Decimal,
        branch_id: str,
        target_id: str,
        evidence: dict[str, str],
        title: str,
        message: str,
        now: datetime,
        existing_alerts: tuple[AnalyticalAlert, ...] = (),
    ) -> AnalyticalAlert | None:
        if not rule.enabled:
            return None
        if not rule.is_breached(metric_value):
            return None

        fingerprint = build_fingerprint(rule.alert_type, branch_id, target_id)
        if should_suppress(existing_alerts, fingerprint, rule.cooldown_minutes, now):
            return None

        return AnalyticalAlert(
            id=new_uuid(), rule_id=rule.id, alert_type=rule.alert_type, severity=rule.severity,
            title=title, message=message, branch_id=branch_id, target_id=target_id,
            evidence=evidence, fingerprint=fingerprint, status=AlertStatus.OPEN, created_at=now,
        )
