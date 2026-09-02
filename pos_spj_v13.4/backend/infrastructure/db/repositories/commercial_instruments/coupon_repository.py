"""CouponDefinitionRepository / CouponInstanceRepository /
CouponRedemptionRepository — persist/reconstruct the Commercial Instruments
entities (LOY-12, §21)."""

from __future__ import annotations

from backend.domain.commercial_instruments.entities.coupon_definition import CouponDefinition
from backend.domain.commercial_instruments.entities.coupon_instance import CouponInstance
from backend.domain.commercial_instruments.entities.coupon_redemption import CouponRedemption
from backend.domain.commercial_instruments.enums import (
    CommercialBenefitType,
    CouponInstanceStatus,
    CouponType,
)
from backend.infrastructure.db.repositories.commercial_instruments.base import (
    CommercialInstrumentsRepositoryBase,
    bool_to_int,
    dec_str,
    int_to_bool,
    to_decimal,
)


class CouponDefinitionRepository(CommercialInstrumentsRepositoryBase):
    def save(self, definition: CouponDefinition) -> None:
        self._execute(
            """
            INSERT INTO coupon_definitions (
                id, code, name, coupon_type, benefit_type, benefit_value,
                max_redemptions_per_instance, valid_from, valid_to, source_program_id,
                active, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                benefit_value=excluded.benefit_value,
                valid_from=excluded.valid_from,
                valid_to=excluded.valid_to,
                active=excluded.active,
                updated_at=excluded.updated_at
            """,
            (
                definition.id, definition.code, definition.name,
                definition.coupon_type.value, definition.benefit_type.value,
                dec_str(definition.benefit_value), definition.max_redemptions_per_instance,
                definition.valid_from, definition.valid_to, definition.source_program_id,
                bool_to_int(definition.active), definition.created_at, definition.updated_at,
            ),
        )

    def get(self, definition_id: str) -> CouponDefinition | None:
        row = self._query_one("SELECT * FROM coupon_definitions WHERE id=?", (definition_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CouponDefinition | None:
        row = self._query_one("SELECT * FROM coupon_definitions WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> CouponDefinition:
        return CouponDefinition(
            id=row["id"], code=row["code"], name=row["name"],
            coupon_type=CouponType(row["coupon_type"]),
            benefit_type=CommercialBenefitType(row["benefit_type"]),
            benefit_value=to_decimal(row["benefit_value"]),
            max_redemptions_per_instance=row["max_redemptions_per_instance"],
            valid_from=row["valid_from"], valid_to=row["valid_to"],
            source_program_id=row["source_program_id"], active=int_to_bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


class CouponInstanceRepository(CommercialInstrumentsRepositoryBase):
    def save(self, instance: CouponInstance) -> None:
        self._execute(
            """
            INSERT INTO coupon_instances (
                id, definition_id, code, status, customer_id, sale_id, issued_at,
                reserved_at, redeemed_at, closed_at, closed_reason
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                sale_id=excluded.sale_id,
                reserved_at=excluded.reserved_at,
                redeemed_at=excluded.redeemed_at,
                closed_at=excluded.closed_at,
                closed_reason=excluded.closed_reason
            """,
            (
                instance.id, instance.definition_id, instance.code, instance.status.value,
                instance.customer_id, instance.sale_id, instance.issued_at,
                instance.reserved_at, instance.redeemed_at, instance.closed_at,
                instance.closed_reason,
            ),
        )

    def get(self, instance_id: str) -> CouponInstance | None:
        row = self._query_one("SELECT * FROM coupon_instances WHERE id=?", (instance_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CouponInstance | None:
        row = self._query_one("SELECT * FROM coupon_instances WHERE code=?", (code,))
        return self._hydrate(row) if row else None

    def list_expirable(self, *, definition_ids: list[str], limit: int = 500) -> list[CouponInstance]:
        if not definition_ids:
            return []
        placeholders = ",".join("?" for _ in definition_ids)
        rows = self._query(
            f"SELECT * FROM coupon_instances WHERE definition_id IN ({placeholders})"
            " AND status IN ('ISSUED','ACTIVE') LIMIT ?",
            (*definition_ids, limit))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> CouponInstance:
        return CouponInstance(
            id=row["id"], definition_id=row["definition_id"], code=row["code"],
            status=CouponInstanceStatus(row["status"]), customer_id=row["customer_id"],
            sale_id=row["sale_id"], issued_at=row["issued_at"],
            reserved_at=row["reserved_at"], redeemed_at=row["redeemed_at"],
            closed_at=row["closed_at"], closed_reason=row["closed_reason"],
        )


class CouponRedemptionRepository(CommercialInstrumentsRepositoryBase):
    def add(self, redemption: CouponRedemption) -> None:
        self._execute(
            """
            INSERT INTO coupon_redemptions (
                id, coupon_instance_id, sale_id, amount_applied, redeemed_by_user_id,
                redeemed_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (redemption.id, redemption.coupon_instance_id, redemption.sale_id,
             dec_str(redemption.amount_applied), redemption.redeemed_by_user_id,
             redemption.redeemed_at),
        )

    def get_by_instance(self, coupon_instance_id: str) -> CouponRedemption | None:
        row = self._query_one(
            "SELECT * FROM coupon_redemptions WHERE coupon_instance_id=?",
            (coupon_instance_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> CouponRedemption:
        return CouponRedemption(
            id=row["id"], coupon_instance_id=row["coupon_instance_id"], sale_id=row["sale_id"],
            amount_applied=to_decimal(row["amount_applied"]),
            redeemed_by_user_id=row["redeemed_by_user_id"], redeemed_at=row["redeemed_at"],
        )
