"""SET-12 — "DTO": TicketLine/TicketTotals/TicketPaymentSummary/TicketParty/
TicketData. Pure domain — no DB. Decimal end-to-end throughout.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.document_output.enums import DocumentSectionCode, DocumentType
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.document_section import DocumentSection
from backend.domain.document_output.value_objects.section_layout import SectionLayout
from backend.domain.document_output.value_objects.ticket_data import TicketData
from backend.domain.document_output.value_objects.ticket_line import TicketLine
from backend.domain.document_output.value_objects.ticket_party import TicketParty
from backend.domain.document_output.value_objects.ticket_payment_summary import TicketPaymentSummary
from backend.domain.document_output.value_objects.ticket_totals import TicketTotals


def _line(**overrides) -> TicketLine:
    kwargs = dict(
        description="Carne molida", quantity=Decimal("2"), unit_price=Decimal("120.00"),
        line_total=Decimal("240.00"), unit="kg",
    )
    kwargs.update(overrides)
    return TicketLine.create(**kwargs)


class TestTicketLine:
    def test_requires_description(self):
        with pytest.raises(DocumentInvalidValueError):
            _line(description="   ")

    @pytest.mark.parametrize("field_name", ["quantity", "unit_price", "line_total"])
    def test_rejects_float(self, field_name):
        with pytest.raises(DocumentInvalidValueError):
            _line(**{field_name: 1.5})

    def test_rejects_non_positive_quantity(self):
        with pytest.raises(DocumentInvalidValueError):
            _line(quantity=Decimal("0"))

    def test_rejects_negative_unit_price(self):
        with pytest.raises(DocumentInvalidValueError):
            _line(unit_price=Decimal("-1"))

    def test_rejects_negative_line_total(self):
        with pytest.raises(DocumentInvalidValueError):
            _line(line_total=Decimal("-1"))

    def test_defaults_unit_to_pz(self):
        line = TicketLine.create(
            description="Bolsa", quantity=Decimal("1"), unit_price=Decimal("5"), line_total=Decimal("5"),
        )
        assert line.unit == "pz"


class TestTicketTotals:
    def test_valid_totals(self):
        totals = TicketTotals.create(subtotal=Decimal("100"), discount=Decimal("10"), total=Decimal("90"))
        assert totals.total == Decimal("90")

    def test_rejects_mismatched_arithmetic(self):
        with pytest.raises(DocumentInvalidValueError):
            TicketTotals.create(subtotal=Decimal("100"), discount=Decimal("10"), total=Decimal("100"))

    @pytest.mark.parametrize("field_name", ["subtotal", "discount", "total"])
    def test_rejects_negative(self, field_name):
        kwargs = dict(subtotal=Decimal("10"), discount=Decimal("0"), total=Decimal("10"))
        kwargs[field_name] = Decimal("-1")
        with pytest.raises(DocumentInvalidValueError):
            TicketTotals.create(**kwargs)

    def test_rejects_float(self):
        with pytest.raises(DocumentInvalidValueError):
            TicketTotals.create(subtotal=100.0, discount=Decimal("0"), total=Decimal("100"))


class TestTicketPaymentSummary:
    def test_requires_method(self):
        with pytest.raises(DocumentInvalidValueError):
            TicketPaymentSummary.create(method="   ", amount_tendered=Decimal("10"), change_due=Decimal("0"))

    def test_rejects_negative_amounts(self):
        with pytest.raises(DocumentInvalidValueError):
            TicketPaymentSummary.create(
                method="EFECTIVO", amount_tendered=Decimal("-1"), change_due=Decimal("0"),
            )


class TestTicketParty:
    def test_requires_name(self):
        with pytest.raises(DocumentInvalidValueError):
            TicketParty.create(name="   ")

    def test_optional_fields_default_empty_and_trim(self):
        party = TicketParty.create(name="  Carniceria SPJ  ", address="  Calle 1  ")
        assert party.name == "Carniceria SPJ"
        assert party.address == "Calle 1"
        assert party.phone == ""
        assert party.tax_id == ""


class TestTicketDataCreate:
    def _totals_for(self, *lines: TicketLine, discount: Decimal = Decimal("0")) -> TicketTotals:
        subtotal = sum((line.line_total for line in lines), Decimal("0"))
        return TicketTotals.create(subtotal=subtotal, discount=discount, total=subtotal - discount)

    def test_requires_folio(self):
        line = _line()
        with pytest.raises(DocumentInvalidValueError):
            TicketData.create(
                document_type=DocumentType.SALE_TICKET, folio="   ", issued_at="now",
                issuer=TicketParty.create(name="SPJ"), lines=[line], totals=self._totals_for(line),
            )

    def test_requires_at_least_one_line(self):
        with pytest.raises(DocumentInvalidValueError):
            TicketData.create(
                document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
                issuer=TicketParty.create(name="SPJ"), lines=[],
                totals=TicketTotals.create(subtotal=Decimal("0"), discount=Decimal("0"), total=Decimal("0")),
            )

    def test_line_totals_must_sum_to_subtotal(self):
        line1 = _line()
        line2 = _line(description="Bolsa", quantity=Decimal("1"), unit_price=Decimal("5"), line_total=Decimal("5"))
        wrong_totals = TicketTotals.create(subtotal=Decimal("240.00"), discount=Decimal("0"), total=Decimal("240.00"))
        with pytest.raises(DocumentInvalidValueError):
            TicketData.create(
                document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
                issuer=TicketParty.create(name="SPJ"), lines=[line1, line2], totals=wrong_totals,
            )

    def test_valid_ticket_data_end_to_end(self):
        line1 = _line()
        line2 = _line(description="Bolsa", quantity=Decimal("1"), unit_price=Decimal("5"), line_total=Decimal("5"))
        totals = self._totals_for(line1, line2)
        payment = TicketPaymentSummary.create(
            method="EFECTIVO", amount_tendered=Decimal("300"), change_due=Decimal("55"),
        )
        customer = TicketParty.create(name="Cliente Mostrador")
        layout = SectionLayout.create([
            DocumentSection.create(code=DocumentSectionCode.ITEMS, order=0),
            DocumentSection.create(code=DocumentSectionCode.TOTALS, order=1),
        ])
        data = TicketData.create(
            document_type=DocumentType.SALE_TICKET, folio="VNT-001", issued_at="2026-08-21T10:00:00",
            issuer=TicketParty.create(name="Carniceria SPJ"), lines=[line1, line2], totals=totals,
            payment=payment, customer=customer, section_layout=layout,
        )
        assert data.folio == "VNT-001"
        assert data.totals.total == Decimal("245.00")


class TestTicketDataToRenderData:
    def test_decimal_fields_serialize_as_strings_never_floats(self):
        line = _line()
        totals = TicketTotals.create(subtotal=Decimal("240.00"), discount=Decimal("0"), total=Decimal("240.00"))
        data = TicketData.create(
            document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
            issuer=TicketParty.create(name="SPJ"), lines=[line], totals=totals,
        )
        rendered = data.to_render_data()
        assert rendered["totals"]["total"] == "240.00"
        assert isinstance(rendered["totals"]["total"], str)
        assert rendered["lines"][0]["line_total"] == "240.00"
        assert rendered["payment"] is None
        assert rendered["customer"] is None
        assert rendered["sections"] is None

    def test_sections_reflect_enabled_codes_in_order(self):
        line = _line()
        totals = TicketTotals.create(subtotal=Decimal("240.00"), discount=Decimal("0"), total=Decimal("240.00"))
        layout = SectionLayout.create([
            DocumentSection.create(code=DocumentSectionCode.TOTALS, order=1),
            DocumentSection.create(code=DocumentSectionCode.LOGO, order=0),
            DocumentSection.create(code=DocumentSectionCode.QR, order=2, enabled=False),
        ])
        data = TicketData.create(
            document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
            issuer=TicketParty.create(name="SPJ"), lines=[line], totals=totals, section_layout=layout,
        )
        assert data.to_render_data()["sections"] == ["LOGO", "TOTALS"]

    def test_extra_keys_are_merged_into_render_data(self):
        line = _line()
        totals = TicketTotals.create(subtotal=Decimal("240.00"), discount=Decimal("0"), total=Decimal("240.00"))
        data = TicketData.create(
            document_type=DocumentType.SALE_TICKET, folio="VNT-1", issued_at="now",
            issuer=TicketParty.create(name="SPJ"), lines=[line], totals=totals,
            extra={"cashier": "cashier-1"},
        )
        assert data.to_render_data()["cashier"] == "cashier-1"
