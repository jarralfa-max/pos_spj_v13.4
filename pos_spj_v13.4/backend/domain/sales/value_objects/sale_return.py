"""SaleReturn — one recorded partial-line return against a COMPLETED Sale
(POS-16/§42-44). Immutable, same "point-in-time fact, never edited" shape
as `SalePayment` — undoing a return is a new, later operation, never an
edit of this record.

`amount` is the proportional refund this return is worth: `(line.line_total
/ line.quantity.value) * quantity` — line_total is already net of that
line's own discount/tax, so a partial return of a discounted line refunds
the discounted price, not the list price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.sales.exceptions import SaleReturnNotAllowedError
from backend.domain.sales.value_objects.money import money
from backend.shared.ids import new_uuid, validate_uuidv7


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class SaleReturn:
    id: str
    sale_id: str
    line_id: str
    quantity: Decimal
    amount: Decimal
    reason: str
    requested_by_user_id: str
    authorized_by_user_id: str
    created_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, sale_id: str, line_id: str, quantity: Decimal, amount: Decimal, reason: str,
        requested_by_user_id: str, authorized_by_user_id: str,
    ) -> "SaleReturn":
        validate_uuidv7(sale_id)
        validate_uuidv7(line_id)
        validate_uuidv7(requested_by_user_id)
        validate_uuidv7(authorized_by_user_id)
        if not (reason or "").strip():
            raise SaleReturnNotAllowedError("La devolución requiere un motivo")
        return cls(
            id=new_uuid(), sale_id=sale_id, line_id=line_id, quantity=quantity,
            amount=money(amount, allow_zero=False), reason=reason.strip(),
            requested_by_user_id=requested_by_user_id,
            authorized_by_user_id=authorized_by_user_id,
        )
