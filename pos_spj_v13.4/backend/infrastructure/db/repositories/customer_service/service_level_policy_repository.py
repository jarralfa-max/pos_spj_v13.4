"""ServiceLevelPolicyRepository — persists the configurable SLA policy
catalog."""

from __future__ import annotations

from backend.domain.customer_service.entities.service_level_policy import ServiceLevelPolicy
from backend.domain.customer_service.enums import (
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseType,
)
from backend.infrastructure.db.repositories.customer_service.base import (
    CustomerServiceRepositoryBase,
)

_POLICY_COLS = (
    "id, code, name, first_response_minutes, resolution_minutes, case_type,"
    " priority, origin_branch_id, channel, at_risk_threshold_pct, active,"
    " created_at, updated_at"
)


class ServiceLevelPolicyRepository(CustomerServiceRepositoryBase):
    def save(self, policy: ServiceLevelPolicy) -> None:
        self._execute(
            f"INSERT INTO service_level_policies ({_POLICY_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            self._params(policy))

    def update(self, policy: ServiceLevelPolicy) -> None:
        self._execute(
            "UPDATE service_level_policies SET name=?, first_response_minutes=?,"
            " resolution_minutes=?, case_type=?, priority=?, origin_branch_id=?, channel=?,"
            " at_risk_threshold_pct=?, active=?, updated_at=? WHERE id=?",
            (policy.name, policy.first_response_minutes, policy.resolution_minutes,
             policy.case_type.value if policy.case_type else None,
             policy.priority.value if policy.priority else None, policy.origin_branch_id,
             policy.channel.value if policy.channel else None, policy.at_risk_threshold_pct,
             int(policy.active), policy.updated_at, policy.id))

    def get(self, policy_id: str) -> ServiceLevelPolicy | None:
        row = self._query_one(
            f"SELECT {_POLICY_COLS} FROM service_level_policies WHERE id=?", (policy_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[ServiceLevelPolicy]:
        rows = self._query(
            f"SELECT {_POLICY_COLS} FROM service_level_policies WHERE active=1")
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(policy: ServiceLevelPolicy) -> tuple:
        return (
            policy.id, policy.code, policy.name, policy.first_response_minutes,
            policy.resolution_minutes, policy.case_type.value if policy.case_type else None,
            policy.priority.value if policy.priority else None, policy.origin_branch_id,
            policy.channel.value if policy.channel else None, policy.at_risk_threshold_pct,
            int(policy.active), policy.created_at, policy.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> ServiceLevelPolicy:
        return ServiceLevelPolicy(
            id=row["id"], code=row["code"], name=row["name"],
            first_response_minutes=row["first_response_minutes"],
            resolution_minutes=row["resolution_minutes"],
            case_type=ServiceCaseType(row["case_type"]) if row["case_type"] else None,
            priority=ServiceCasePriority(row["priority"]) if row["priority"] else None,
            origin_branch_id=row["origin_branch_id"],
            channel=ServiceCaseChannel(row["channel"]) if row["channel"] else None,
            at_risk_threshold_pct=row["at_risk_threshold_pct"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
