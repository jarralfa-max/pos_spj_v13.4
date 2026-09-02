"""SET-15 — "Boleto": SweepstakesTicketData. Pure domain — no DB."""

from __future__ import annotations

import pytest

from backend.domain.document_output.enums import DocumentSectionCode
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.document_section import DocumentSection
from backend.domain.document_output.value_objects.section_layout import SectionLayout
from backend.domain.document_output.value_objects.sweepstakes_ticket_data import SweepstakesTicketData
from backend.domain.document_output.value_objects.ticket_party import TicketParty
from backend.shared.ids import new_uuid


def _ticket(**overrides) -> SweepstakesTicketData:
    kwargs = dict(
        raffle_id=new_uuid(), raffle_name="Rifa de Verano", ticket_number="0001234",
        prize="Refrigerador", draw_date="2026-09-15",
    )
    kwargs.update(overrides)
    return SweepstakesTicketData.create(**kwargs)


class TestSweepstakesTicketDataCreate:
    def test_valid_minimal_ticket(self):
        ticket = _ticket()
        assert ticket.ticket_number == "0001234"
        assert ticket.customer is None
        assert ticket.section_layout is None

    def test_validates_raffle_id_as_uuid(self):
        with pytest.raises(ValueError):
            _ticket(raffle_id="not-a-uuid")

    def test_requires_raffle_name(self):
        with pytest.raises(DocumentInvalidValueError):
            _ticket(raffle_name="   ")

    def test_requires_ticket_number(self):
        with pytest.raises(DocumentInvalidValueError):
            _ticket(ticket_number="   ")

    def test_requires_prize(self):
        with pytest.raises(DocumentInvalidValueError):
            _ticket(prize="   ")

    def test_requires_draw_date(self):
        with pytest.raises(DocumentInvalidValueError):
            _ticket(draw_date="   ")

    def test_optional_fields_default_empty(self):
        ticket = _ticket()
        assert ticket.footer_message == ""
        assert ticket.legal_message == ""
        assert ticket.sale_reference is None
        assert ticket.qr_payload is None
        assert ticket.barcode is None

    def test_accepts_customer_and_sale_reference(self):
        ticket = _ticket(customer=TicketParty.create(name="Juan Pérez"), sale_reference="VNT-001")
        assert ticket.customer.name == "Juan Pérez"
        assert ticket.sale_reference == "VNT-001"


class TestSweepstakesTicketDataToRenderData:
    def test_flattens_scalar_fields(self):
        rendered = _ticket().to_render_data()
        assert rendered["raffle_name"] == "Rifa de Verano"
        assert rendered["ticket_number"] == "0001234"
        assert rendered["prize"] == "Refrigerador"
        assert rendered["draw_date"] == "2026-09-15"
        assert rendered["customer"] is None
        assert rendered["sections"] is None

    def test_customer_flattens_to_dict(self):
        ticket = _ticket(customer=TicketParty.create(name="Juan Pérez", phone="555-1234"))
        rendered = ticket.to_render_data()
        assert rendered["customer"] == {
            "name": "Juan Pérez", "address": "", "phone": "555-1234", "tax_id": "",
        }

    def test_sections_reflect_enabled_codes_in_order(self):
        layout = SectionLayout.create([
            DocumentSection.create(code=DocumentSectionCode.PRIZE, order=1),
            DocumentSection.create(code=DocumentSectionCode.RAFFLE_TITLE, order=0),
            DocumentSection.create(code=DocumentSectionCode.DRAW_DATE, order=2, enabled=False),
        ])
        ticket = _ticket(section_layout=layout)
        assert ticket.to_render_data()["sections"] == ["RAFFLE_TITLE", "PRIZE"]
