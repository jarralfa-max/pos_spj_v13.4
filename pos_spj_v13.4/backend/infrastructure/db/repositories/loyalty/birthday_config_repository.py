"""BirthdayBenefitConfigRepository — persist/reconstruct
`BirthdayBenefitConfig` (LOY-14, §18)."""

from __future__ import annotations

from backend.domain.loyalty.entities.birthday_benefit_config import BirthdayBenefitConfig
from backend.domain.loyalty.enums import BirthdayBenefitType
from backend.infrastructure.db.repositories.loyalty.base import (
    LoyaltyRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class BirthdayBenefitConfigRepository(LoyaltyRepositoryBase):
    def save(self, config: BirthdayBenefitConfig) -> None:
        self._execute(
            """
            INSERT INTO loyalty_birthday_configs (
                id, program_id, enabled, benefit_type, points_amount,
                coupon_definition_id, voucher_definition_id, reward_id, days_before,
                days_after, notification_channel, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                enabled=excluded.enabled,
                benefit_type=excluded.benefit_type,
                points_amount=excluded.points_amount,
                coupon_definition_id=excluded.coupon_definition_id,
                voucher_definition_id=excluded.voucher_definition_id,
                reward_id=excluded.reward_id,
                days_before=excluded.days_before,
                days_after=excluded.days_after,
                notification_channel=excluded.notification_channel,
                updated_at=excluded.updated_at
            """,
            (
                config.id, config.program_id, bool_to_int(config.enabled),
                config.benefit_type.value, dec_str(config.points_amount),
                config.coupon_definition_id, config.voucher_definition_id, config.reward_id,
                config.days_before, config.days_after, config.notification_channel,
                config.created_at, config.updated_at,
            ),
        )

    def get_by_program(self, program_id: str) -> BirthdayBenefitConfig | None:
        row = self._query_one(
            "SELECT * FROM loyalty_birthday_configs WHERE program_id=?", (program_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> BirthdayBenefitConfig:
        return BirthdayBenefitConfig(
            id=row["id"], program_id=row["program_id"], enabled=int_to_bool(row["enabled"]),
            benefit_type=BirthdayBenefitType(row["benefit_type"]),
            points_amount=to_decimal(row["points_amount"]),
            coupon_definition_id=row["coupon_definition_id"],
            voucher_definition_id=row["voucher_definition_id"], reward_id=row["reward_id"],
            days_before=row["days_before"], days_after=row["days_after"],
            notification_channel=row["notification_channel"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
