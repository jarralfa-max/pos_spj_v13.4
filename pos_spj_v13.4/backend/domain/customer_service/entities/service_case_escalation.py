"""ServiceCaseEscalation — an immutable record of one escalation event
(§30-32: "Registra motivo/nivel/usuario/fecha/destinatario"). Mirrors
backend/domain/crm/entities/opportunity_stage_history.py — written once per
``EscalateServiceCaseUseCase`` call, never updated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_service.enums import EscalationReason
from backend.domain.customer_service.exceptions import CustomerServiceDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ServiceCaseEscalation:
    id: str
    case_id: str
    reason: EscalationReason
    level: int
    escalated_to_user_id: str
    escalated_by_user_id: str
    detail: str = ""
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, case_id: str, reason: EscalationReason, level: int, escalated_to_user_id: str,
        escalated_by_user_id: str, *, detail: str = "",
    ) -> "ServiceCaseEscalation":
        if not case_id:
            raise CustomerServiceDomainError("ServiceCaseEscalation requiere case_id")
        if not escalated_to_user_id:
            raise CustomerServiceDomainError("Escalar requiere un destinatario")
        if not escalated_by_user_id:
            raise CustomerServiceDomainError("Escalar requiere quién escaló")
        if level < 1:
            raise CustomerServiceDomainError("level debe ser al menos 1")
        return cls(
            id=new_uuid(), case_id=case_id, reason=reason, level=level,
            escalated_to_user_id=escalated_to_user_id,
            escalated_by_user_id=escalated_by_user_id, detail=detail,
        )
