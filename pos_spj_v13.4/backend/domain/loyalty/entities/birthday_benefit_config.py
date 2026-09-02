"""BirthdayBenefitConfig — per-program birthday benefit configuration
(master prompt §18). No hardcoded amounts/day-windows anywhere in code —
every value is a field on this entity, configured per program.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.enums import BirthdayBenefitType
from backend.domain.loyalty.exceptions import InvalidBirthdayBenefitConfigError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class BirthdayBenefitConfig:
    id: str
    program_id: str
    enabled: bool = True
    benefit_type: BirthdayBenefitType = BirthdayBenefitType.NONE
    points_amount: Decimal = Decimal("0")
    coupon_definition_id: str | None = None
    voucher_definition_id: str | None = None
    reward_id: str | None = None
    days_before: int = 0
    days_after: int = 0
    notification_channel: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.program_id:
            raise InvalidBirthdayBenefitConfigError("program_id es obligatorio")
        if self.days_before < 0 or self.days_after < 0:
            raise InvalidBirthdayBenefitConfigError("days_before/days_after no pueden ser negativos")
        if self.benefit_type is BirthdayBenefitType.POINTS and self.points_amount <= 0:
            raise InvalidBirthdayBenefitConfigError(
                "benefit_type POINTS requiere points_amount positivo")
        if self.benefit_type is BirthdayBenefitType.COUPON and not self.coupon_definition_id:
            raise InvalidBirthdayBenefitConfigError(
                "benefit_type COUPON requiere coupon_definition_id")
        if self.benefit_type is BirthdayBenefitType.VOUCHER:
            if not self.voucher_definition_id:
                raise InvalidBirthdayBenefitConfigError(
                    "benefit_type VOUCHER requiere voucher_definition_id")
            if self.points_amount <= 0:
                # LOY-24: `points_amount` doubles as the voucher's face
                # amount — vouchers have no fixed face value on their own
                # `VoucherDefinition` (unlike coupons' own `benefit_value`),
                # so this is the only place a birthday voucher's amount can
                # come from.
                raise InvalidBirthdayBenefitConfigError(
                    "benefit_type VOUCHER requiere points_amount positivo (monto del vale)")
        if self.benefit_type is BirthdayBenefitType.REWARD and not self.reward_id:
            raise InvalidBirthdayBenefitConfigError(
                "benefit_type REWARD requiere reward_id")

    @classmethod
    def create(cls, program_id: str, **kwargs) -> "BirthdayBenefitConfig":
        return cls(id=new_uuid(), program_id=program_id, **kwargs)

    def disable(self) -> None:
        self.enabled = False
        self.updated_at = _utcnow()

    def enable(self) -> None:
        self.enabled = True
        self.updated_at = _utcnow()
