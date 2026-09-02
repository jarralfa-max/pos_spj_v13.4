"""CouponDefinition — a configured coupon offer (master prompt §21).

Not scoped to a LoyaltyProgram by default (``source_program_id`` is
optional) — coupons are commercial instruments independent of any loyalty
program (``SUPPLIER_FUNDED``/``EMPLOYEE_GRANTED`` are never loyalty
concepts at all); a coupon originating from a reward redemption
(``LOYALTY_REWARD``) records which program it came from without belonging
to that bounded context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.commercial_instruments.enums import CommercialBenefitType, CouponType
from backend.domain.commercial_instruments.exceptions import InvalidCouponDefinitionError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CouponDefinition:
    id: str
    code: str
    name: str
    coupon_type: CouponType
    benefit_type: CommercialBenefitType
    benefit_value: Decimal
    max_redemptions_per_instance: int = 1
    valid_from: str | None = None
    valid_to: str | None = None
    source_program_id: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.code or not self.code.strip():
            raise InvalidCouponDefinitionError("code es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidCouponDefinitionError("name es obligatorio")
        if isinstance(self.benefit_value, bool) or isinstance(self.benefit_value, float):
            raise InvalidCouponDefinitionError("benefit_value debe ser Decimal, nunca float")
        self.benefit_value = Decimal(str(self.benefit_value))
        if self.benefit_value <= 0:
            raise InvalidCouponDefinitionError("benefit_value debe ser positivo")
        if self.max_redemptions_per_instance <= 0:
            raise InvalidCouponDefinitionError("max_redemptions_per_instance debe ser positivo")

    @classmethod
    def create(
        cls, code: str, name: str, coupon_type: CouponType,
        benefit_type: CommercialBenefitType, benefit_value: Decimal, **kwargs,
    ) -> "CouponDefinition":
        return cls(id=new_uuid(), code=code.strip(), name=name.strip(),
                   coupon_type=coupon_type, benefit_type=benefit_type,
                   benefit_value=benefit_value, **kwargs)

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _utcnow()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _utcnow()
