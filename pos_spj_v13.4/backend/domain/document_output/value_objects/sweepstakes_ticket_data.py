"""SweepstakesTicketData — SET-15 "Boleto": the typed aggregate a module
assembles before calling `rendering_ports.DocumentRendererPort.render()`
for `DocumentType.SWEEPSTAKES_TICKET`, the raffle-boleto counterpart to
SET-12's `TicketData` and SET-14's `LabelData`. Generalizes the payload
`core/services/loyalty_service.py::LoyaltyService._raffle_print_payload`
already builds for `core/tickets/raffle_ticket_renderer.py::
RaffleTicketESCPOSRenderer` — same fields (raffle name, ticket number,
prize, draw date, customer, sale reference), reusing SET-12's
`TicketParty` for the customer rather than a bare name string.

`raffle_id`/`sale_reference` are opaque references back into the
sweepstakes/loyalty domain — this entity never resolves or validates
them, the same discipline `PrintJob.source_module`/`source_document_id`
already apply (SET-11).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.section_layout import SectionLayout
from backend.domain.document_output.value_objects.ticket_party import TicketParty
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class SweepstakesTicketData:
    raffle_id: str
    raffle_name: str
    ticket_number: str
    prize: str
    draw_date: str
    customer: TicketParty | None = None
    sale_reference: str | None = None
    qr_payload: str | None = None
    barcode: str | None = None
    footer_message: str = ""
    legal_message: str = ""
    section_layout: SectionLayout | None = None

    @classmethod
    def create(
        cls, *, raffle_id: str, raffle_name: str, ticket_number: str, prize: str, draw_date: str,
        customer: TicketParty | None = None, sale_reference: str | None = None,
        qr_payload: str | None = None, barcode: str | None = None, footer_message: str = "",
        legal_message: str = "", section_layout: SectionLayout | None = None,
    ) -> "SweepstakesTicketData":
        if not raffle_name.strip():
            raise DocumentInvalidValueError("raffle_name es obligatorio")
        if not ticket_number.strip():
            raise DocumentInvalidValueError("ticket_number es obligatorio")
        if not prize.strip():
            raise DocumentInvalidValueError("prize es obligatorio")
        if not draw_date.strip():
            raise DocumentInvalidValueError("draw_date es obligatorio")
        return cls(
            raffle_id=validate_uuidv7(raffle_id), raffle_name=raffle_name.strip(),
            ticket_number=ticket_number.strip(), prize=prize.strip(), draw_date=draw_date.strip(),
            customer=customer, sale_reference=sale_reference, qr_payload=qr_payload, barcode=barcode,
            footer_message=footer_message.strip(), legal_message=legal_message.strip(),
            section_layout=section_layout,
        )

    def to_render_data(self) -> dict:
        """Flattens this DTO into the plain, JSON-serializable ``data``
        dict `DocumentRendererPort.render()` already expects — mirrors
        `TicketData.to_render_data()`/`LabelData.to_render_data()`."""
        return {
            "raffle_id": self.raffle_id, "raffle_name": self.raffle_name,
            "ticket_number": self.ticket_number, "prize": self.prize, "draw_date": self.draw_date,
            "customer": (
                {
                    "name": self.customer.name, "address": self.customer.address,
                    "phone": self.customer.phone, "tax_id": self.customer.tax_id,
                }
                if self.customer else None
            ),
            "sale_reference": self.sale_reference, "qr_payload": self.qr_payload, "barcode": self.barcode,
            "footer_message": self.footer_message, "legal_message": self.legal_message,
            "sections": (
                [code.value for code in self.section_layout.enabled_codes()]
                if self.section_layout else None
            ),
        }
