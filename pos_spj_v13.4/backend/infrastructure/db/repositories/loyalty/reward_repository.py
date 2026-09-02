"""RewardRepository / RewardRedemptionRepository — persist/reconstruct
`Reward`/`RewardRedemption` (LOY-8, §15)."""

from __future__ import annotations

from backend.domain.loyalty.entities.reward import Reward
from backend.domain.loyalty.entities.reward_redemption import RewardRedemption
from backend.domain.loyalty.enums import RewardRedemptionStatus, RewardType
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class RewardRepository(LoyaltyRepositoryBase):
    def save(self, reward: Reward) -> None:
        self._execute(
            """
            INSERT INTO loyalty_rewards (
                id, program_id, code, name, reward_type, points_cost, description,
                value, active, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                points_cost=excluded.points_cost,
                description=excluded.description,
                value=excluded.value,
                active=excluded.active,
                updated_at=excluded.updated_at
            """,
            (
                reward.id, reward.program_id, reward.code, reward.name,
                reward.reward_type.value, dec_str(reward.points_cost),
                reward.description, dec_str(reward.value), bool_to_int(reward.active),
                reward.created_at, reward.updated_at,
            ),
        )

    def get(self, reward_id: str) -> Reward | None:
        row = self._query_one("SELECT * FROM loyalty_rewards WHERE id=?", (reward_id,))
        return self._hydrate(row) if row else None

    def list_active_for_program(self, program_id: str) -> list[Reward]:
        rows = self._query(
            "SELECT * FROM loyalty_rewards WHERE program_id=? AND active=1 ORDER BY name",
            (program_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> Reward:
        return Reward(
            id=row["id"], program_id=row["program_id"], code=row["code"], name=row["name"],
            reward_type=RewardType(row["reward_type"]), points_cost=to_decimal(row["points_cost"]),
            description=row["description"], value=to_decimal(row["value"]),
            active=int_to_bool(row["active"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class RewardRedemptionRepository(LoyaltyRepositoryBase):
    def save(self, redemption: RewardRedemption) -> None:
        self._execute(
            """
            INSERT INTO loyalty_reward_redemptions (
                id, reward_id, membership_id, loyalty_account_id, points_transaction_id,
                status, sale_id, requested_at, confirmed_at, cancelled_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                confirmed_at=excluded.confirmed_at,
                cancelled_at=excluded.cancelled_at
            """,
            (
                redemption.id, redemption.reward_id, redemption.membership_id,
                redemption.loyalty_account_id, redemption.points_transaction_id,
                redemption.status.value, redemption.sale_id, redemption.requested_at,
                redemption.confirmed_at, redemption.cancelled_at,
            ),
        )

    def get(self, redemption_id: str) -> RewardRedemption | None:
        row = self._query_one(
            "SELECT * FROM loyalty_reward_redemptions WHERE id=?", (redemption_id,))
        return self._hydrate(row) if row else None

    def list_for_membership(self, membership_id: str) -> list[RewardRedemption]:
        rows = self._query(
            "SELECT * FROM loyalty_reward_redemptions WHERE membership_id=?"
            " ORDER BY requested_at", (membership_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> RewardRedemption:
        return RewardRedemption(
            id=row["id"], reward_id=row["reward_id"], membership_id=row["membership_id"],
            loyalty_account_id=row["loyalty_account_id"],
            points_transaction_id=row["points_transaction_id"],
            status=RewardRedemptionStatus(row["status"]), sale_id=row["sale_id"],
            requested_at=row["requested_at"], confirmed_at=row["confirmed_at"],
            cancelled_at=row["cancelled_at"],
        )
