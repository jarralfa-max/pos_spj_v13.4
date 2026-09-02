"""LoyaltyMembershipRepository — persists/reconstructs `LoyaltyMembership`
against `loyalty_memberships`."""

from __future__ import annotations

from backend.domain.loyalty.entities.loyalty_membership import LoyaltyMembership
from backend.domain.loyalty.enums import MembershipStatus
from backend.infrastructure.db.repositories.loyalty.base import LoyaltyRepositoryBase


class LoyaltyMembershipRepository(LoyaltyRepositoryBase):
    def save(self, membership: LoyaltyMembership) -> None:
        self._execute(
            """
            INSERT INTO loyalty_memberships (
                id, loyalty_account_id, program_id, current_tier_id, status,
                enrolled_at, suspended_at, closed_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                current_tier_id=excluded.current_tier_id,
                status=excluded.status,
                suspended_at=excluded.suspended_at,
                closed_at=excluded.closed_at,
                updated_at=excluded.updated_at
            """,
            (
                membership.id, membership.loyalty_account_id, membership.program_id,
                membership.current_tier_id, membership.status.value,
                membership.enrolled_at, membership.suspended_at, membership.closed_at,
                membership.updated_at,
            ),
        )

    def get(self, membership_id: str) -> LoyaltyMembership | None:
        row = self._query_one(
            "SELECT * FROM loyalty_memberships WHERE id=?", (membership_id,))
        return self._hydrate(row) if row else None

    def get_by_account_and_program(
        self, loyalty_account_id: str, program_id: str,
    ) -> LoyaltyMembership | None:
        row = self._query_one(
            "SELECT * FROM loyalty_memberships WHERE loyalty_account_id=? AND program_id=?",
            (loyalty_account_id, program_id))
        return self._hydrate(row) if row else None

    def list_for_account(self, loyalty_account_id: str) -> list[LoyaltyMembership]:
        rows = self._query(
            "SELECT * FROM loyalty_memberships WHERE loyalty_account_id=?"
            " ORDER BY enrolled_at", (loyalty_account_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyMembership:
        return LoyaltyMembership(
            id=row["id"], loyalty_account_id=row["loyalty_account_id"],
            program_id=row["program_id"], current_tier_id=row["current_tier_id"],
            status=MembershipStatus(row["status"]), enrolled_at=row["enrolled_at"],
            suspended_at=row["suspended_at"], closed_at=row["closed_at"],
            updated_at=row["updated_at"],
        )
