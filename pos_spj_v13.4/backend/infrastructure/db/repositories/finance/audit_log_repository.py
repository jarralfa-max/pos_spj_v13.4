"""Bitácora de auditoría financiera (§25). Sólo se agrega; nunca se edita ni borra."""

from __future__ import annotations

from backend.domain.finance.entities.audit_record import AuditRecord
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


class FinanceAuditLogRepository(FinanceRepositoryBase):
    def append(self, record: AuditRecord) -> None:
        self._insert("finance_audit_log", {
            "id": record.id, "action": record.action.value, "entity_type": record.entity_type,
            "entity_id": record.entity_id, "operation_id": record.operation_id,
            "user_id": record.user_id, "before_json": record.before_json,
            "after_json": record.after_json, "reason": record.reason,
            "branch_id": record.branch_id, "occurred_at": record.occurred_at,
        })

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM finance_audit_log WHERE entity_type=? AND entity_id=?"
            " ORDER BY occurred_at", (entity_type, entity_id))
