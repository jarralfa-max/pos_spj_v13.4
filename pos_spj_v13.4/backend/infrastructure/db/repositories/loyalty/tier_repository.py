"""LoyaltyTierRepository / LoyaltyTierHistoryRepository — persist/reconstruct
`LoyaltyTier`/`LoyaltyTierHistory` (LOY-7, §14).

`LoyaltyTierHistoryRepository` only ever INSERTs — the entity itself is
frozen and append-only, so there is no update path to expose."""

from __future__ import annotations

from backend.domain.loyalty.entities.loyalty_tier import LoyaltyTier
from backend.domain.loyalty.entities.loyalty_tier_history import LoyaltyTierHistory
from backend.domain.loyalty.enums import TierEvaluationMethod
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class LoyaltyTierRepository(LoyaltyRepositoryBase):
    def save(self, tier: LoyaltyTier) -> None:
        self._execute(
            """
            INSERT INTO loyalty_tiers (
                id, program_id, code, name, rank, minimum_points, minimum_spend,
                minimum_visits, evaluation_method, evaluation_window_days,
                benefit_multiplier, effective_from, effective_to, active,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                rank=excluded.rank,
                minimum_points=excluded.minimum_points,
                minimum_spend=excluded.minimum_spend,
                minimum_visits=excluded.minimum_visits,
                evaluation_method=excluded.evaluation_method,
                evaluation_window_days=excluded.evaluation_window_days,
                benefit_multiplier=excluded.benefit_multiplier,
                effective_from=excluded.effective_from,
                effective_to=excluded.effective_to,
                active=excluded.active,
                updated_at=excluded.updated_at
            """,
            (
                tier.id, tier.program_id, tier.code, tier.name, tier.rank,
                dec_str(tier.minimum_points), dec_str(tier.minimum_spend),
                tier.minimum_visits, tier.evaluation_method.value,
                tier.evaluation_window_days, dec_str(tier.benefit_multiplier),
                tier.effective_from, tier.effective_to, bool_to_int(tier.active),
                tier.created_at, tier.updated_at,
            ),
        )

    def get(self, tier_id: str) -> LoyaltyTier | None:
        row = self._query_one("SELECT * FROM loyalty_tiers WHERE id=?", (tier_id,))
        return self._hydrate(row) if row else None

    def list_active_for_program(self, program_id: str) -> list[LoyaltyTier]:
        rows = self._query(
            "SELECT * FROM loyalty_tiers WHERE program_id=? AND active=1 ORDER BY rank",
            (program_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyTier:
        return LoyaltyTier(
            id=row["id"], program_id=row["program_id"], code=row["code"], name=row["name"],
            rank=row["rank"], minimum_points=to_decimal(row["minimum_points"]),
            minimum_spend=to_decimal(row["minimum_spend"]), minimum_visits=row["minimum_visits"],
            evaluation_method=TierEvaluationMethod(row["evaluation_method"]),
            evaluation_window_days=row["evaluation_window_days"],
            benefit_multiplier=to_decimal(row["benefit_multiplier"], default="1"),
            effective_from=row["effective_from"], effective_to=row["effective_to"],
            active=int_to_bool(row["active"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class LoyaltyTierHistoryRepository(LoyaltyRepositoryBase):
    def add(self, entry: LoyaltyTierHistory) -> None:
        self._execute(
            """
            INSERT INTO loyalty_tier_history (
                id, membership_id, previous_tier_id, new_tier_id, reason, evaluated_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (entry.id, entry.membership_id, entry.previous_tier_id, entry.new_tier_id,
             entry.reason, entry.evaluated_at),
        )

    def list_for_membership(self, membership_id: str) -> list[LoyaltyTierHistory]:
        rows = self._query(
            "SELECT * FROM loyalty_tier_history WHERE membership_id=? ORDER BY evaluated_at",
            (membership_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyTierHistory:
        return LoyaltyTierHistory(
            id=row["id"], membership_id=row["membership_id"],
            previous_tier_id=row["previous_tier_id"], new_tier_id=row["new_tier_id"],
            reason=row["reason"], evaluated_at=row["evaluated_at"],
        )
