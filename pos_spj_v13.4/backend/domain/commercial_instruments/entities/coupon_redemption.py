"""CouponRedemption — an immutable audit record of one confirmed redemption
(master prompt §21). Append-only, mirrors `LoyaltyTierHistory`/`LoyaltyBadge`'s
frozen shape — the live state lives on `CouponInstance` itself, this is only
the historical trail."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.commercial_instruments.exceptions import InvalidCouponInstanceStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class CouponRedemption:
    id: str
    coupon_instance_id: str
    sale_id: str
    amount_applied: Decimal
    redeemed_by_user_id: str
    redeemed_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.coupon_instance_id:
            raise InvalidCouponInstanceStateError("coupon_instance_id es obligatorio")
        if not self.sale_id:
            raise InvalidCouponInstanceStateError("sale_id es obligatorio")
        if isinstance(self.amount_applied, bool) or isinstance(self.amount_applied, float):
            raise InvalidCouponInstanceStateError("amount_applied debe ser Decimal, nunca float")
        object.__setattr__(self, "amount_applied", Decimal(str(self.amount_applied)))

    @classmethod
    def record(cls, coupon_instance_id: str, sale_id: str, amount_applied: Decimal,
               redeemed_by_user_id: str) -> "CouponRedemption":
        return cls(id=new_uuid(), coupon_instance_id=coupon_instance_id, sale_id=sale_id,
                   amount_applied=amount_applied, redeemed_by_user_id=redeemed_by_user_id)
