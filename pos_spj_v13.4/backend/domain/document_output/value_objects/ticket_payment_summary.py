"""TicketPaymentSummary — SET-12 "DTO". Decimal end-to-end; generalizes
the legacy float-based
`core/tickets/ticket_print_model.py::TicketPaymentInfo`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.document_output.exceptions import DocumentInvalidValueError


def _assert_decimal(value: Decimal, field_name: str) -> None:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise DocumentInvalidValueError(f"{field_name} debe ser Decimal, nunca float, recibido {value!r}")


@dataclass(frozen=True, slots=True)
class TicketPaymentSummary:
    method: str
    amount_tendered: Decimal
    change_due: Decimal

    @classmethod
    def create(
        cls, *, method: str, amount_tendered: Decimal, change_due: Decimal,
    ) -> "TicketPaymentSummary":
        if not method.strip():
            raise DocumentInvalidValueError("method es obligatorio")
        _assert_decimal(amount_tendered, "amount_tendered")
        _assert_decimal(change_due, "change_due")
        if amount_tendered < 0:
            raise DocumentInvalidValueError(f"amount_tendered no puede ser negativo, recibido {amount_tendered!r}")
        if change_due < 0:
            raise DocumentInvalidValueError(f"change_due no puede ser negativo, recibido {change_due!r}")
        return cls(method=method.strip(), amount_tendered=amount_tendered, change_due=change_due)
