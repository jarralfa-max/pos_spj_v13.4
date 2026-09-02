"""VoucherRedemption — an immutable audit record of ONE partial or full
redemption event (master prompt §22). Unlike `CouponRedemption` (exactly one
per instance), a voucher instance can have several of these across its
lifetime — partial redemption is a first-class feature here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.commercial_instruments.exceptions import (
    InvalidVoucherInstanceStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class VoucherRedemption:
    id: str
    voucher_instance_id: str
    sale_id: str
    amount_applied: Decimal
    redeemed_by_user_id: str
    redeemed_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.voucher_instance_id:
            raise InvalidVoucherInstanceStateError("voucher_instance_id es obligatorio")
        if not self.sale_id:
            raise InvalidVoucherInstanceStateError("sale_id es obligatorio")
        if isinstance(self.amount_applied, bool) or isinstance(self.amount_applied, float):
            raise InvalidVoucherInstanceStateError("amount_applied debe ser Decimal, nunca float")
        object.__setattr__(self, "amount_applied", Decimal(str(self.amount_applied)))
        if self.amount_applied <= 0:
            raise InvalidVoucherInstanceStateError("amount_applied debe ser positivo")

    @classmethod
    def record(cls, voucher_instance_id: str, sale_id: str, amount_applied: Decimal,
               redeemed_by_user_id: str) -> "VoucherRedemption":
        return cls(id=new_uuid(), voucher_instance_id=voucher_instance_id, sale_id=sale_id,
                   amount_applied=amount_applied, redeemed_by_user_id=redeemed_by_user_id)
