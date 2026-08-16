"""CRMAutomationExecution — audit/log row for one firing of a
CRMAutomationRule (§76: toda automatización deja evidencia). Append-only,
mirrors the CustomerConsent/CustomerOwnership "capture-only" shape already
established elsewhere in this bounded context — an execution is never
edited after the fact, only created.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import CRMAutomationExecutionStatus
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CRMAutomationExecution:
    id: str
    rule_id: str
    trigger_type: str
    target_entity_type: str
    target_entity_id: str
    status: CRMAutomationExecutionStatus
    result_detail: str = ""
    created_entity_id: str | None = None
    operation_id: str = ""
    executed_at: str = field(default_factory=_utcnow)

    @classmethod
    def record(
        cls, rule_id: str, trigger_type: str, target_entity_type: str, target_entity_id: str,
        status: CRMAutomationExecutionStatus, *, result_detail: str = "",
        created_entity_id: str | None = None, operation_id: str = "",
    ) -> "CRMAutomationExecution":
        return cls(
            id=new_uuid(), rule_id=rule_id, trigger_type=trigger_type,
            target_entity_type=target_entity_type, target_entity_id=target_entity_id,
            status=status, result_detail=result_detail, created_entity_id=created_entity_id,
            operation_id=operation_id,
        )
