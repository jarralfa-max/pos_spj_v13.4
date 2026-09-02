"""TicketTotals — SET-12 "DTO". Decimal end-to-end; generalizes the
legacy float-based `core/tickets/ticket_print_model.py::TicketTotals`.

Enforces the one real arithmetic invariant a totals block must satisfy —
`total == subtotal - discount` — catching the classic "an item was added
to the sale but never reached the printed total" bug class at
construction time rather than on a printed receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.document_output.exceptions import DocumentInvalidValueError


def _assert_decimal(value: Decimal, field_name: str) -> None:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise DocumentInvalidValueError(f"{field_name} debe ser Decimal, nunca float, recibido {value!r}")


@dataclass(frozen=True, slots=True)
class TicketTotals:
    subtotal: Decimal
    discount: Decimal
    total: Decimal

    @classmethod
    def create(cls, *, subtotal: Decimal, discount: Decimal, total: Decimal) -> "TicketTotals":
        _assert_decimal(subtotal, "subtotal")
        _assert_decimal(discount, "discount")
        _assert_decimal(total, "total")
        if subtotal < 0:
            raise DocumentInvalidValueError(f"subtotal no puede ser negativo, recibido {subtotal!r}")
        if discount < 0:
            raise DocumentInvalidValueError(f"discount no puede ser negativo, recibido {discount!r}")
        if total < 0:
            raise DocumentInvalidValueError(f"total no puede ser negativo, recibido {total!r}")
        if total != subtotal - discount:
            raise DocumentInvalidValueError(
                f"total ({total}) debe ser igual a subtotal - discount ({subtotal - discount})"
            )
        return cls(subtotal=subtotal, discount=discount, total=total)
