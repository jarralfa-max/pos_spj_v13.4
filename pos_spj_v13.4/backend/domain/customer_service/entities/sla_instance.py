"""SLAInstance — the SLA clock attached to one CustomerServiceCase
(§30-32: "first_response_due_at, resolution_due_at, first_response_at,
resolved_at, breach_status, escalation_level").

``breach_status`` is split between stored and derived, same reasoning as
CRMWorkItemStatus.OVERDUE (CRM-6): PAUSED and COMPLETED are explicit,
event-driven states (the case entered WAITING_CUSTOMER; a resolution was
recorded) so they ARE persisted fields (``paused``, ``resolved_at``).
ON_TIME/AT_RISK/BREACHED depend purely on wall-clock time passing without
action, so they are never persisted — ``effective_breach_status()``
computes them from ``resolution_due_at`` vs. "now", the same way
``CRMActivity.effective_status()`` derives OVERDUE.

Pausing does NOT push ``resolution_due_at`` back by the paused duration in
this phase — it only freezes the *displayed* status at PAUSED while the
case is legitimately waiting on the customer, not our fault. A precise
"extend the deadline by the paused interval" refinement is a reasonable
future improvement, not implemented here (documented, not silently
skipped) — same kind of scoped simplification as CRM-5's forecast
"stagnant" approximation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from backend.domain.customer_service.enums import SLABreachStatus
from backend.domain.customer_service.exceptions import InvalidSLAInstanceError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class SLAInstance:
    id: str
    case_id: str
    policy_id: str
    first_response_due_at: str
    resolution_due_at: str
    at_risk_threshold_pct: int = 80
    first_response_at: str | None = None
    resolved_at: str | None = None
    paused: bool = False
    escalation_level: int = 0
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, case_id: str, policy_id: str, first_response_minutes: int, resolution_minutes: int,
        *, at_risk_threshold_pct: int = 80, reference_time: str | None = None,
    ) -> "SLAInstance":
        if not case_id:
            raise InvalidSLAInstanceError("SLAInstance requiere case_id")
        if not policy_id:
            raise InvalidSLAInstanceError("SLAInstance requiere policy_id")
        created = reference_time or _utcnow()
        base = _parse(created)
        return cls(
            id=new_uuid(), case_id=case_id, policy_id=policy_id,
            first_response_due_at=(base + timedelta(minutes=first_response_minutes)).isoformat(
                timespec="seconds"),
            resolution_due_at=(base + timedelta(minutes=resolution_minutes)).isoformat(
                timespec="seconds"),
            at_risk_threshold_pct=at_risk_threshold_pct, created_at=created,
        )

    def record_first_response(self, *, at: str | None = None) -> None:
        if self.first_response_at is not None:
            raise InvalidSLAInstanceError("Ya se registró la primera respuesta")
        self.first_response_at = at or _utcnow()

    def record_resolution(self, *, at: str | None = None) -> None:
        if self.resolved_at is not None:
            raise InvalidSLAInstanceError("Ya se registró la resolución")
        self.resolved_at = at or _utcnow()
        self.paused = False

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def bump_escalation(self) -> int:
        self.escalation_level += 1
        return self.escalation_level

    def effective_breach_status(self, *, as_of: str | None = None) -> SLABreachStatus:
        if self.resolved_at is not None:
            return SLABreachStatus.COMPLETED
        if self.paused:
            return SLABreachStatus.PAUSED
        now = as_of or _utcnow()
        if now > self.resolution_due_at:
            return SLABreachStatus.BREACHED
        total = (_parse(self.resolution_due_at) - _parse(self.created_at)).total_seconds()
        elapsed = (_parse(now) - _parse(self.created_at)).total_seconds()
        if total > 0 and (elapsed / total * 100) >= self.at_risk_threshold_pct:
            return SLABreachStatus.AT_RISK
        return SLABreachStatus.ON_TIME
