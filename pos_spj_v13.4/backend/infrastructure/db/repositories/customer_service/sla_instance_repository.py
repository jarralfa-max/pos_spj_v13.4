"""SLAInstanceRepository — persists the SLA clock attached to a case."""

from __future__ import annotations

from backend.domain.customer_service.entities.sla_instance import SLAInstance
from backend.infrastructure.db.repositories.customer_service.base import (
    CustomerServiceRepositoryBase,
)

_SLA_COLS = (
    "id, case_id, policy_id, first_response_due_at, resolution_due_at,"
    " at_risk_threshold_pct, first_response_at, resolved_at, paused,"
    " escalation_level, created_at"
)


class SLAInstanceRepository(CustomerServiceRepositoryBase):
    def save(self, instance: SLAInstance) -> None:
        self._execute(
            f"INSERT INTO sla_instances ({_SLA_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            self._params(instance))

    def update(self, instance: SLAInstance) -> None:
        self._execute(
            "UPDATE sla_instances SET first_response_at=?, resolved_at=?, paused=?,"
            " escalation_level=? WHERE id=?",
            (instance.first_response_at, instance.resolved_at, int(instance.paused),
             instance.escalation_level, instance.id))

    def get_for_case(self, case_id: str) -> SLAInstance | None:
        row = self._query_one(f"SELECT {_SLA_COLS} FROM sla_instances WHERE case_id=?",
                              (case_id,))
        return self._hydrate(row) if row else None

    def list_open(self, *, limit: int = 500, offset: int = 0) -> list[SLAInstance]:
        rows = self._query(
            f"SELECT {_SLA_COLS} FROM sla_instances WHERE resolved_at IS NULL"
            " ORDER BY resolution_due_at ASC LIMIT ? OFFSET ?", (limit, offset))
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(instance: SLAInstance) -> tuple:
        return (
            instance.id, instance.case_id, instance.policy_id, instance.first_response_due_at,
            instance.resolution_due_at, instance.at_risk_threshold_pct,
            instance.first_response_at, instance.resolved_at, int(instance.paused),
            instance.escalation_level, instance.created_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> SLAInstance:
        return SLAInstance(
            id=row["id"], case_id=row["case_id"], policy_id=row["policy_id"],
            first_response_due_at=row["first_response_due_at"],
            resolution_due_at=row["resolution_due_at"],
            at_risk_threshold_pct=row["at_risk_threshold_pct"],
            first_response_at=row["first_response_at"], resolved_at=row["resolved_at"],
            paused=bool(row["paused"]), escalation_level=row["escalation_level"],
            created_at=row["created_at"],
        )
