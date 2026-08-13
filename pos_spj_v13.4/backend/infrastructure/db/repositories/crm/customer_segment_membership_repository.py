"""CustomerSegmentMembershipRepository — persists CustomerSegmentMembership
records (append-only-with-nullable-removed_at — see
backend/domain/crm/entities/customer_segment_membership.py).
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_segment_membership import (
    CustomerSegmentMembership,
)
from backend.domain.crm.enums import SegmentMembershipSource
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = (
    "id, customer_id, segment_id, source, added_by_user_id, removed_at,"
    " removed_by_user_id, operation_id, created_at"
)


class CustomerSegmentMembershipRepository(CRMRepositoryBase):
    def save(self, membership: CustomerSegmentMembership, *,
             operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_segment_memberships ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?)",
            self._params(membership, operation_id or membership.operation_id))

    def update(self, membership: CustomerSegmentMembership) -> None:
        self._execute(
            "UPDATE customer_segment_memberships SET removed_at=?, removed_by_user_id=?"
            " WHERE id=?",
            (membership.removed_at, membership.removed_by_user_id, membership.id))

    def get(self, membership_id: str) -> CustomerSegmentMembership | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_segment_memberships WHERE id=?", (membership_id,))
        return self._hydrate(row) if row else None

    def get_active(self, customer_id: str, segment_id: str) -> CustomerSegmentMembership | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_segment_memberships"
            " WHERE customer_id=? AND segment_id=? AND removed_at IS NULL"
            " ORDER BY created_at DESC, id DESC LIMIT 1",
            (customer_id, segment_id))
        return self._hydrate(row) if row else None

    def list_active_for_customer(self, customer_id: str) -> list[CustomerSegmentMembership]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_segment_memberships"
            " WHERE customer_id=? AND removed_at IS NULL ORDER BY created_at DESC, id DESC",
            (customer_id,))
        return [self._hydrate(r) for r in rows]

    def list_for_segment(self, segment_id: str) -> list[CustomerSegmentMembership]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_segment_memberships"
            " WHERE segment_id=? ORDER BY created_at DESC, id DESC", (segment_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(membership: CustomerSegmentMembership, operation_id: str | None) -> tuple:
        return (
            membership.id, membership.customer_id, membership.segment_id,
            membership.source.value, membership.added_by_user_id, membership.removed_at,
            membership.removed_by_user_id, operation_id, membership.created_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerSegmentMembership:
        return CustomerSegmentMembership(
            id=row["id"], customer_id=row["customer_id"], segment_id=row["segment_id"],
            source=SegmentMembershipSource(row["source"]),
            added_by_user_id=row["added_by_user_id"], removed_at=row["removed_at"],
            removed_by_user_id=row["removed_by_user_id"], operation_id=row["operation_id"],
            created_at=row["created_at"],
        )
