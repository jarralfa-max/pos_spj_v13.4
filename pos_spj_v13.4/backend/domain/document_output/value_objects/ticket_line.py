"""TicketLine — SET-12 "DTO": one priced line of a ticket. Decimal
end-to-end (CLAUDE.md regla 11/REGLA CERO's Decimal discipline) —
generalizes the legacy float-based
`core/tickets/ticket_print_model.py::TicketItem` for the new bounded
context's typed DTO layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.document_output.exceptions import DocumentInvalidValueError


def _assert_decimal(value: Decimal, field_name: str) -> None:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, Decimal):
        raise DocumentInvalidValueError(f"{field_name} debe ser Decimal, nunca float, recibido {value!r}")


@dataclass(frozen=True, slots=True)
class TicketLine:
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    unit: str = "pz"

    @classmethod
    def create(
        cls, *, description: str, quantity: Decimal, unit_price: Decimal, line_total: Decimal,
        unit: str = "pz",
    ) -> "TicketLine":
        if not description.strip():
            raise DocumentInvalidValueError("description es obligatoria")
        _assert_decimal(quantity, "quantity")
        _assert_decimal(unit_price, "unit_price")
        _assert_decimal(line_total, "line_total")
        if quantity <= 0:
            raise DocumentInvalidValueError(f"quantity debe ser > 0, recibido {quantity!r}")
        if unit_price < 0:
            raise DocumentInvalidValueError(f"unit_price no puede ser negativo, recibido {unit_price!r}")
        if line_total < 0:
            raise DocumentInvalidValueError(f"line_total no puede ser negativo, recibido {line_total!r}")
        return cls(
            description=description.strip(), quantity=quantity, unit_price=unit_price,
            line_total=line_total, unit=(unit or "pz").strip(),
        )
