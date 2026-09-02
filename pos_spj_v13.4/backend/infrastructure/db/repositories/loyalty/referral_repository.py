"""ReferralRepository — persist/reconstruct `Referral` (LOY-10, §17)."""

from __future__ import annotations

from backend.domain.loyalty.entities.referral import Referral
from backend.domain.loyalty.enums import ReferralStatus
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    dec_str,
    to_decimal,
)


class ReferralRepository(LoyaltyRepositoryBase):
    def save(self, referral: Referral) -> None:
        self._execute(
            """
            INSERT INTO loyalty_referrals (
                id, program_id, referrer_membership_id, referred_customer_id,
                referrer_bonus_points, referred_bonus_points, minimum_purchase_amount,
                status, registered_at, qualified_at, rewarded_at, closed_at,
                closed_reason, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                qualified_at=excluded.qualified_at,
                rewarded_at=excluded.rewarded_at,
                closed_at=excluded.closed_at,
                closed_reason=excluded.closed_reason
            """,
            (
                referral.id, referral.program_id, referral.referrer_membership_id,
                referral.referred_customer_id, dec_str(referral.referrer_bonus_points),
                dec_str(referral.referred_bonus_points),
                dec_str(referral.minimum_purchase_amount), referral.status.value,
                referral.registered_at, referral.qualified_at, referral.rewarded_at,
                referral.closed_at, referral.closed_reason, referral.expires_at,
            ),
        )

    def get(self, referral_id: str) -> Referral | None:
        row = self._query_one("SELECT * FROM loyalty_referrals WHERE id=?", (referral_id,))
        return self._hydrate(row) if row else None

    def list_for_referrer(self, referrer_membership_id: str) -> list[Referral]:
        rows = self._query(
            "SELECT * FROM loyalty_referrals WHERE referrer_membership_id=?"
            " ORDER BY registered_at", (referrer_membership_id,))
        return [self._hydrate(row) for row in rows]

    def count_rewarded_for_referrer_since(
        self, referrer_membership_id: str, since_iso: str,
    ) -> int:
        """Supports a monthly-cap rule (§17: 'máximo mensual') without
        fabricating the rule engine itself — the caller decides the window
        and the cap, this just counts."""
        return self._scalar(
            "SELECT COUNT(*) FROM loyalty_referrals WHERE referrer_membership_id=?"
            " AND status='REWARDED' AND rewarded_at >= ?",
            (referrer_membership_id, since_iso), default=0)

    @staticmethod
    def _hydrate(row: dict) -> Referral:
        return Referral(
            id=row["id"], program_id=row["program_id"],
            referrer_membership_id=row["referrer_membership_id"],
            referred_customer_id=row["referred_customer_id"],
            referrer_bonus_points=to_decimal(row["referrer_bonus_points"]),
            referred_bonus_points=to_decimal(row["referred_bonus_points"]),
            minimum_purchase_amount=to_decimal(row["minimum_purchase_amount"]),
            status=ReferralStatus(row["status"]), registered_at=row["registered_at"],
            qualified_at=row["qualified_at"], rewarded_at=row["rewarded_at"],
            closed_at=row["closed_at"], closed_reason=row["closed_reason"],
            expires_at=row["expires_at"],
        )
