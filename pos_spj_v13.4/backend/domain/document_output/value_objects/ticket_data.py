"""TicketData — SET-12 "DTO": the typed, Decimal-safe aggregate a module
assembles before calling `rendering_ports.DocumentRendererPort.render()`
(§27: "La plantilla no consulta tablas."). Generalizes the legacy
float-based `core/tickets/ticket_print_model.py::TicketPrintModel` into
the new bounded context — one shape any module (sales, purchases,
transfers, production...) can build from its own data, rather than each
module inventing its own dict shape as
`backend/application/sales/dto.py::SaleReceiptDataDTO` did for Sales
specifically (SALES-17). That Sales-specific DTO is untouched by this
SET — see `MIGRATION_LOG.md`'s SET-12 entry for why cutting Sales over is
out of scope here.

Enforces the one real cross-object invariant: the sum of `lines[].line_total`
must equal `totals.subtotal` — catches a line silently missing from the
total at construction time.

SET-13 "Loyalty summary" adds `loyalty` (a `LoyaltySummary`, generalizing
legacy `TicketLoyaltyInfo`) and `messages` (final rendered marketing
strings, already selected/capped by
`policies/marketing_claim_validation_policy.py::select_messages` —
`TicketData` never selects or validates campaigns itself, only carries
the result). Both default to their empty state so every SET-12 caller
that predates this SET keeps constructing valid `TicketData` unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.document_output.enums import DocumentType
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.loyalty_summary import LoyaltySummary
from backend.domain.document_output.value_objects.section_layout import SectionLayout
from backend.domain.document_output.value_objects.ticket_payment_summary import TicketPaymentSummary
from backend.domain.document_output.value_objects.ticket_party import TicketParty
from backend.domain.document_output.value_objects.ticket_totals import TicketTotals
from backend.domain.document_output.value_objects.ticket_line import TicketLine


@dataclass(frozen=True, slots=True)
class TicketData:
    document_type: DocumentType
    folio: str
    issued_at: str
    issuer: TicketParty
    lines: tuple[TicketLine, ...]
    totals: TicketTotals
    payment: TicketPaymentSummary | None = None
    customer: TicketParty | None = None
    section_layout: SectionLayout | None = None
    loyalty: LoyaltySummary | None = None
    messages: tuple[str, ...] = ()
    extra: dict = field(default_factory=dict)

    @classmethod
    def create(
        cls, *, document_type: DocumentType, folio: str, issued_at: str, issuer: TicketParty,
        lines: tuple[TicketLine, ...] | list[TicketLine], totals: TicketTotals,
        payment: TicketPaymentSummary | None = None, customer: TicketParty | None = None,
        section_layout: SectionLayout | None = None, loyalty: LoyaltySummary | None = None,
        messages: tuple[str, ...] | list[str] = (), extra: dict | None = None,
    ) -> "TicketData":
        if not folio.strip():
            raise DocumentInvalidValueError("folio es obligatorio")
        lines = tuple(lines)
        if not lines:
            raise DocumentInvalidValueError("TicketData requiere al menos una línea")
        lines_sum = sum((line.line_total for line in lines), Decimal("0"))
        if lines_sum != totals.subtotal:
            raise DocumentInvalidValueError(
                f"La suma de lines[].line_total ({lines_sum}) no coincide con totals.subtotal ({totals.subtotal})"
            )
        return cls(
            document_type=document_type, folio=folio.strip(), issued_at=issued_at, issuer=issuer,
            lines=lines, totals=totals, payment=payment, customer=customer,
            section_layout=section_layout, loyalty=loyalty, messages=tuple(messages),
            extra=dict(extra or {}),
        )

    def to_render_data(self) -> dict:
        """Flattens this DTO into the plain, JSON-serializable ``data``
        dict `DocumentRendererPort.render()` already expects — Decimal
        fields become strings (never floats), the same discipline
        `backend/infrastructure/db/repositories/settings/value_serialization.py`
        uses for persisted Decimal values."""
        data = {
            "document_type": self.document_type.value,
            "folio": self.folio,
            "issued_at": self.issued_at,
            "issuer": {
                "name": self.issuer.name, "address": self.issuer.address,
                "phone": self.issuer.phone, "tax_id": self.issuer.tax_id,
            },
            "lines": [
                {
                    "description": line.description, "quantity": str(line.quantity),
                    "unit_price": str(line.unit_price), "line_total": str(line.line_total),
                    "unit": line.unit,
                }
                for line in self.lines
            ],
            "totals": {
                "subtotal": str(self.totals.subtotal), "discount": str(self.totals.discount),
                "total": str(self.totals.total),
            },
            "payment": (
                {
                    "method": self.payment.method, "amount_tendered": str(self.payment.amount_tendered),
                    "change_due": str(self.payment.change_due),
                }
                if self.payment else None
            ),
            "customer": (
                {
                    "name": self.customer.name, "address": self.customer.address,
                    "phone": self.customer.phone, "tax_id": self.customer.tax_id,
                }
                if self.customer else None
            ),
            "sections": (
                [code.value for code in self.section_layout.enabled_codes()]
                if self.section_layout else None
            ),
            "loyalty": (
                {
                    "points_earned": self.loyalty.points_earned, "points_balance": self.loyalty.points_balance,
                    "tier": self.loyalty.tier, "available": self.loyalty.available,
                }
                if self.loyalty else None
            ),
            "messages": list(self.messages),
        }
        data.update(self.extra)
        return data
