"""AnalyticalAlert (§46/§50, BI-20) — lifecycle state + audit trail
(`acknowledged_by`/`resolved_by`/`reason`/timestamps, §50)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from backend.domain.analytical_alerting.enums import AlertSeverity, AlertStatus, AlertType
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class AnalyticalAlert:
    id: str
    rule_id: str
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    branch_id: str
    target_id: str
    evidence: dict[str, str]
    fingerprint: str
    status: AlertStatus
    created_at: datetime
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        validate_uuidv7(self.id)
        validate_uuidv7(self.rule_id)
        for name in ("title", "message", "branch_id", "target_id", "fingerprint"):
            if not getattr(self, name):
                raise ValueError(f"AnalyticalAlert.{name} is required")
        if not self.evidence:
            raise ValueError("AnalyticalAlert.evidence must not be empty")
        if bool(self.acknowledged_by) != bool(self.acknowledged_at):
            raise ValueError("acknowledged_by and acknowledged_at must be set together")
        if bool(self.resolved_by) != bool(self.resolved_at):
            raise ValueError("resolved_by and resolved_at must be set together")
        if self.resolved_by is not None and not self.reason:
            raise ValueError("reason is required once resolved_by is set (§50)")
        if self.status in (AlertStatus.RESOLVED, AlertStatus.DISMISSED) and self.resolved_by is None:
            raise ValueError(f"status={self.status} requires resolved_by/resolved_at/reason")

    def is_terminal(self) -> bool:
        return self.status in (AlertStatus.RESOLVED, AlertStatus.DISMISSED, AlertStatus.EXPIRED)
