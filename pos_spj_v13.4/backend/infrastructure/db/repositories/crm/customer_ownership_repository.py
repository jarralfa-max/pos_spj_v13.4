"""CustomerOwnershipRepository — persists CustomerOwnership evidence
records (append-only per (customer, ownership_type) — see
backend/domain/crm/entities/customer_ownership.py). Mirrors
backend/infrastructure/db/repositories/customer_privacy/customer_consent_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_ownership import CustomerOwnership
from backend.domain.crm.enums import OwnershipType
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = (
    "id, customer_id, ownership_type, owner_user_id, assigned_by_user_id, reason,"
    " operation_id, created_at"
)


class CustomerOwnershipRepository(CRMRepositoryBase):
    def save(self, ownership: CustomerOwnership, *, operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_ownerships ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            self._params(ownership, operation_id or ownership.operation_id))

    def get_latest(self, customer_id: str, ownership_type: str) -> CustomerOwnership | None:
        # created_at has only second precision; id (UUIDv7, time-ordered to
        # sub-millisecond precision) is the deterministic tiebreaker — same
        # fix as CustomerConsentRepository.get_latest().
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_ownerships"
            " WHERE customer_id=? AND ownership_type=? ORDER BY created_at DESC, id DESC LIMIT 1",
            (customer_id, ownership_type))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[CustomerOwnership]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_ownerships"
            " WHERE customer_id=? ORDER BY created_at DESC, id DESC", (customer_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(ownership: CustomerOwnership, operation_id: str | None) -> tuple:
        return (
            ownership.id, ownership.customer_id, ownership.ownership_type.value,
            ownership.owner_user_id, ownership.assigned_by_user_id, ownership.reason,
            operation_id, ownership.created_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerOwnership:
        return CustomerOwnership(
            id=row["id"], customer_id=row["customer_id"],
            ownership_type=OwnershipType(row["ownership_type"]),
            owner_user_id=row["owner_user_id"], assigned_by_user_id=row["assigned_by_user_id"],
            reason=row["reason"] or "", operation_id=row["operation_id"],
            created_at=row["created_at"],
        )
