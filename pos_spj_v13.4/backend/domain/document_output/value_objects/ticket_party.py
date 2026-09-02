"""TicketParty — SET-12 "DTO": a named party printed on a ticket, either
the issuer (generalizes legacy
`core/tickets/ticket_print_model.py::TicketBranding`) or the customer
(generalizes the bare `cliente_nombre` string) — same shape, different
role, so one value object covers both instead of two near-duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.exceptions import DocumentInvalidValueError


@dataclass(frozen=True, slots=True)
class TicketParty:
    name: str
    address: str = ""
    phone: str = ""
    tax_id: str = ""

    @classmethod
    def create(
        cls, *, name: str, address: str = "", phone: str = "", tax_id: str = "",
    ) -> "TicketParty":
        if not name.strip():
            raise DocumentInvalidValueError("name es obligatorio")
        return cls(name=name.strip(), address=address.strip(), phone=phone.strip(), tax_id=tax_id.strip())
