"""LOY-22 — print_renderer (master prompt §50-51)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError
from backend.infrastructure.loyalty_cards.print_renderer import PrintUnit, render_batch_pdf

_SCHEMA = {
    "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
    "elements": [
        {"type": "TEXT", "x_mm": "5", "y_mm": "5", "width_mm": "40", "height_mm": "8",
         "content": "{{customer_name}}"},
        {"type": "QR", "x_mm": "60", "y_mm": "5", "width_mm": "20", "height_mm": "20",
         "data_source": "CARD_TOKEN"},
        {"type": "BARCODE", "x_mm": "5", "y_mm": "40", "width_mm": "50", "height_mm": "10",
         "format": "CODE128", "data_source": "CARD_NUMBER"},
        {"type": "SHAPE", "x_mm": "0", "y_mm": "0", "width_mm": "85.6", "height_mm": "54",
         "shape_type": "RECTANGLE"},
        {"type": "IMAGE", "x_mm": "30", "y_mm": "30", "width_mm": "10", "height_mm": "10",
         "source": "LOGO"},
    ],
}


def _unit(card_id="card1", sheet=1, position=1, **values) -> PrintUnit:
    defaults = {"customer_name": "Juan Pérez", "card_token": "tok-abc", "card_number": "LC-001"}
    defaults.update(values)
    return PrintUnit(card_id=card_id, sheet_number=sheet, position_in_sheet=position,
                      placeholder_values=defaults)


def _kwargs(**overrides):
    base = dict(
        sheet_width_mm=Decimal("304.8"), sheet_height_mm=Decimal("457.2"),
        margin_left_mm=Decimal("5"), margin_top_mm=Decimal("5"), columns=3, rows=3,
        card_width_mm=Decimal("85.6"), card_height_mm=Decimal("54"), bleed_mm=Decimal("0"),
        gutter_horizontal_mm=Decimal("3"), gutter_vertical_mm=Decimal("3"),
        design_schema=_SCHEMA, print_units=[_unit()])
    base.update(overrides)
    return base


class TestRenderBatchPdf:
    def test_produces_valid_pdf(self):
        pdf = render_batch_pdf(**_kwargs())
        assert pdf[:5] == b"%PDF-"
        assert pdf.rstrip().endswith(b"%%EOF")

    def test_multiple_sheets_produce_multiple_pages(self):
        units = [_unit(card_id="c1", sheet=1, position=1), _unit(card_id="c2", sheet=2, position=1)]
        pdf = render_batch_pdf(**_kwargs(print_units=units))
        # reportlab writes one /Type /Page object per page in the object stream.
        assert pdf.count(b"/Type /Page") >= 2 or pdf.count(b"/Type/Page") >= 2

    def test_scales_to_different_card_size(self):
        pdf_normal = render_batch_pdf(**_kwargs())
        pdf_scaled = render_batch_pdf(**_kwargs(card_width_mm=Decimal("50"), card_height_mm=Decimal("30")))
        assert pdf_normal != pdf_scaled

    def test_empty_print_units_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            render_batch_pdf(**_kwargs(print_units=[]))

    def test_missing_placeholder_rejected(self):
        unit = PrintUnit(card_id="c1", sheet_number=1, position_in_sheet=1,
                          placeholder_values={"card_token": "t", "card_number": "n"})
        with pytest.raises(InvalidCardDesignSchemaError):
            render_batch_pdf(**_kwargs(print_units=[unit]))

    def test_missing_qr_value_rejected(self):
        unit = PrintUnit(card_id="c1", sheet_number=1, position_in_sheet=1,
                          placeholder_values={"customer_name": "x", "card_number": "n"})
        with pytest.raises(InvalidCardDesignSchemaError):
            render_batch_pdf(**_kwargs(print_units=[unit]))

    def test_missing_barcode_value_rejected(self):
        unit = PrintUnit(card_id="c1", sheet_number=1, position_in_sheet=1,
                          placeholder_values={"customer_name": "x", "card_token": "t"})
        with pytest.raises(InvalidCardDesignSchemaError):
            render_batch_pdf(**_kwargs(print_units=[unit]))

    def test_position_out_of_range_rejected(self):
        unit = _unit(position=99)
        with pytest.raises(InvalidCardDesignSchemaError):
            render_batch_pdf(**_kwargs(print_units=[unit]))

    def test_full_sheet_of_units_renders(self):
        units = [_unit(card_id=f"c{i}", position=i) for i in range(1, 10)]
        pdf = render_batch_pdf(**_kwargs(print_units=units))
        assert pdf[:5] == b"%PDF-"
