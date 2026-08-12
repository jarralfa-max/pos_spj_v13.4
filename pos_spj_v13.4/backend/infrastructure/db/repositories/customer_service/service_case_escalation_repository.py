"""ServiceCaseEscalationRepository — append-only log of escalation events."""

from __future__ import annotations

from backend.domain.customer_service.entities.service_case_escalation import (
    ServiceCaseEscalation,
)
from backend.domain.customer_service.enums import EscalationReason
from backend.infrastructure.db.repositories.customer_service.base import (
    CustomerServiceRepositoryBase,
)

_ESCALATION_COLS = (
    "id, case_id, reason, level, escalated_to_user_id, escalated_by_user_id,"
    " detail, created_at"
)


class ServiceCaseEscalationRepository(CustomerServiceRepositoryBase):
    def save(self, escalation: ServiceCaseEscalation) -> None:
        self._execute(
            f"INSERT INTO service_case_escalations ({_ESCALATION_COLS})"
            " VALUES (?,?,?,?,?,?,?,?)",
            (escalation.id, escalation.case_id, escalation.reason.value, escalation.level,
             escalation.escalated_to_user_id, escalation.escalated_by_user_id,
             escalation.detail, escalation.created_at))

    def list_for_case(self, case_id: str) -> list[ServiceCaseEscalation]:
        rows = self._query(
            f"SELECT {_ESCALATION_COLS} FROM service_case_escalations"
            " WHERE case_id=? ORDER BY created_at ASC", (case_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> ServiceCaseEscalation:
        return ServiceCaseEscalation(
            id=row["id"], case_id=row["case_id"], reason=EscalationReason(row["reason"]),
            level=row["level"], escalated_to_user_id=row["escalated_to_user_id"],
            escalated_by_user_id=row["escalated_by_user_id"], detail=row["detail"] or "",
            created_at=row["created_at"],
        )
