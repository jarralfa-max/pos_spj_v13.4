"""SalePayment — one recorded payment line against a Sale (POS-13/§30-36).

Immutable, like `SaleLine`'s own `product_snapshot` philosophy — a payment
line is a point-in-time fact ("this much was captured via this method, with
this reference"), never mutated after the fact. Reversing/refunding a
payment is a different, later operation (§42-48, not this phase) that would
record a NEW line or a cancellation, never edit this one in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.sales.enums import PaymentMethod
from backend.domain.sales.value_objects.money import money
from backend.shared.ids import new_uuid, validate_uuidv7


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class SalePayment:
    id: str
    sale_id: str
    method: PaymentMethod
    amount: Decimal
    captured_by_user_id: str
    reference: str | None = None
    captured_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, sale_id: str, method: PaymentMethod, amount: Decimal,
        captured_by_user_id: str, reference: str | None = None,
    ) -> "SalePayment":
        validate_uuidv7(sale_id)
        validate_uuidv7(captured_by_user_id)
        return cls(
            id=new_uuid(), sale_id=sale_id, method=method,
            amount=money(amount, allow_zero=False), captured_by_user_id=captured_by_user_id,
            reference=(reference or "").strip() or None,
        )
