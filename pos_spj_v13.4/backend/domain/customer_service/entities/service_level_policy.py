"""ServiceLevelPolicy — configurable SLA targets (§30-32: "Configurable
por tipo/prioridad/segmento/sucursal/canal, nunca hardcodeado"). Data, not
a hardcoded enum — mirrors CRMStageDefinition.

Segment matching is deliberately NOT implemented: CRM-10 (Segmentación)
doesn't exist yet, so there is no segment_id to match against. This policy
matches on case_type/priority/origin_branch_id/channel only; add segment_id
when CRM-10 lands rather than guessing its shape now.

``None`` on any matchable field means "applies to all values of that
axis" (a wildcard), not "unset" — ``matches()``/``specificity()`` treat it
that way so the most specific configured policy wins when several could
apply to the same case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_service.enums import (
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseType,
)
from backend.domain.customer_service.exceptions import InvalidServiceLevelPolicyError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ServiceLevelPolicy:
    id: str
    code: str
    name: str
    first_response_minutes: int
    resolution_minutes: int
    case_type: ServiceCaseType | None = None
    priority: ServiceCasePriority | None = None
    origin_branch_id: str | None = None
    channel: ServiceCaseChannel | None = None
    at_risk_threshold_pct: int = 80
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, code: str, name: str, first_response_minutes: int, resolution_minutes: int, *,
        case_type: ServiceCaseType | None = None, priority: ServiceCasePriority | None = None,
        origin_branch_id: str | None = None, channel: ServiceCaseChannel | None = None,
        at_risk_threshold_pct: int = 80,
    ) -> "ServiceLevelPolicy":
        if not code or not code.strip():
            raise InvalidServiceLevelPolicyError("code es obligatorio")
        if not name or not name.strip():
            raise InvalidServiceLevelPolicyError("name es obligatorio")
        if first_response_minutes <= 0:
            raise InvalidServiceLevelPolicyError("first_response_minutes debe ser positivo")
        if resolution_minutes <= 0:
            raise InvalidServiceLevelPolicyError("resolution_minutes debe ser positivo")
        if resolution_minutes < first_response_minutes:
            raise InvalidServiceLevelPolicyError(
                "resolution_minutes no puede ser menor que first_response_minutes")
        if not (0 < at_risk_threshold_pct <= 100):
            raise InvalidServiceLevelPolicyError(
                "at_risk_threshold_pct debe estar entre 1 y 100")
        return cls(
            id=new_uuid(), code=code.strip().upper(), name=name.strip(),
            first_response_minutes=first_response_minutes, resolution_minutes=resolution_minutes,
            case_type=case_type, priority=priority, origin_branch_id=origin_branch_id,
            channel=channel, at_risk_threshold_pct=at_risk_threshold_pct,
        )

    def matches(
        self, *, case_type: ServiceCaseType, priority: ServiceCasePriority,
        origin_branch_id: str | None, channel: ServiceCaseChannel,
    ) -> bool:
        return (
            (self.case_type is None or self.case_type == case_type)
            and (self.priority is None or self.priority == priority)
            and (self.origin_branch_id is None or self.origin_branch_id == origin_branch_id)
            and (self.channel is None or self.channel == channel)
        )

    def specificity(self) -> int:
        """Number of non-wildcard axes — the resolver prefers the highest."""
        return sum(1 for axis in (self.case_type, self.priority, self.origin_branch_id,
                                   self.channel) if axis is not None)

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()
