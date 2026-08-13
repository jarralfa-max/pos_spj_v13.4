"""CustomerDataRetentionPolicyRepository — persists the configurable
retention policy catalog."""

from __future__ import annotations

from backend.domain.customer_privacy.entities.customer_data_retention_policy import (
    CustomerDataRetentionPolicy,
)
from backend.domain.customers.enums import CustomerStatus, CustomerType
from backend.infrastructure.db.repositories.customer_privacy.base import (
    CustomerPrivacyRepositoryBase,
)

_POLICY_COLS = (
    "id, code, name, data_category, retention_days, legal_basis, customer_type,"
    " customer_status, active, created_at, updated_at"
)


class CustomerDataRetentionPolicyRepository(CustomerPrivacyRepositoryBase):
    def save(self, policy: CustomerDataRetentionPolicy) -> None:
        self._execute(
            f"INSERT INTO customer_data_retention_policies ({_POLICY_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            self._params(policy))

    def get(self, policy_id: str) -> CustomerDataRetentionPolicy | None:
        row = self._query_one(
            f"SELECT {_POLICY_COLS} FROM customer_data_retention_policies WHERE id=?",
            (policy_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[CustomerDataRetentionPolicy]:
        rows = self._query(
            f"SELECT {_POLICY_COLS} FROM customer_data_retention_policies WHERE active=1")
        return [self._hydrate(r) for r in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(policy: CustomerDataRetentionPolicy) -> tuple:
        return (
            policy.id, policy.code, policy.name, policy.data_category, policy.retention_days,
            policy.legal_basis, policy.customer_type.value if policy.customer_type else None,
            policy.customer_status.value if policy.customer_status else None,
            int(policy.active), policy.created_at, policy.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerDataRetentionPolicy:
        return CustomerDataRetentionPolicy(
            id=row["id"], code=row["code"], name=row["name"], data_category=row["data_category"],
            retention_days=row["retention_days"], legal_basis=row["legal_basis"] or "",
            customer_type=CustomerType(row["customer_type"]) if row["customer_type"] else None,
            customer_status=(CustomerStatus(row["customer_status"])
                             if row["customer_status"] else None),
            active=bool(row["active"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
