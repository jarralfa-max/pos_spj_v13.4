"""OpportunityStageHistory — an immutable record of one stage move (§19-22).

Written once per ``MoveOpportunityStageUseCase``/``WinOpportunityUseCase``/
``LoseOpportunityUseCase`` call, never updated. ``from_stage_id`` is ``None``
for the very first entry (the stage assigned at creation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.crm.exceptions import CRMDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class OpportunityStageHistory:
    id: str
    opportunity_id: str
    to_stage_id: str
    changed_by_user_id: str
    from_stage_id: str | None = None
    reason: str = ""
    probability: int | None = None
    expected_close_date: date | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, opportunity_id: str, to_stage_id: str, changed_by_user_id: str, *,
        from_stage_id: str | None = None, reason: str = "", probability: int | None = None,
        expected_close_date: date | None = None,
    ) -> "OpportunityStageHistory":
        if not opportunity_id:
            raise CRMDomainError("OpportunityStageHistory requiere opportunity_id")
        if not to_stage_id:
            raise CRMDomainError("OpportunityStageHistory requiere to_stage_id")
        if not changed_by_user_id:
            raise CRMDomainError("OpportunityStageHistory requiere changed_by_user_id")
        return cls(
            id=new_uuid(), opportunity_id=opportunity_id, to_stage_id=to_stage_id,
            changed_by_user_id=changed_by_user_id, from_stage_id=from_stage_id,
            reason=reason, probability=probability, expected_close_date=expected_close_date,
        )
