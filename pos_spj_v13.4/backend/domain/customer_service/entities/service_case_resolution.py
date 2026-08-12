"""ServiceCaseResolution — the evidence a resolution decision leaves behind
(§30-32), mirrors backend/domain/crm/entities/lead_qualification.py's split
from Lead: ``CustomerServiceCase.resolve()`` only flips status, this
records who resolved it, how, and (optionally) the root cause and whether
the customer was satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_service.exceptions import InvalidServiceCaseResolutionError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ServiceCaseResolution:
    id: str
    case_id: str
    resolution_summary: str
    resolved_by_user_id: str
    root_cause: str = ""
    customer_satisfied: bool | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, case_id: str, resolution_summary: str, resolved_by_user_id: str, *,
        root_cause: str = "", customer_satisfied: bool | None = None,
    ) -> "ServiceCaseResolution":
        if not case_id:
            raise InvalidServiceCaseResolutionError("ServiceCaseResolution requiere case_id")
        if not resolution_summary or not resolution_summary.strip():
            raise InvalidServiceCaseResolutionError("resolution_summary es obligatorio")
        if not resolved_by_user_id:
            raise InvalidServiceCaseResolutionError(
                "ServiceCaseResolution requiere resolved_by_user_id")
        return cls(
            id=new_uuid(), case_id=case_id, resolution_summary=resolution_summary.strip(),
            resolved_by_user_id=resolved_by_user_id, root_cause=root_cause,
            customer_satisfied=customer_satisfied,
        )
