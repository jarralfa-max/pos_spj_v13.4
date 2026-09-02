"""Real PDF rendering for a loyalty card batch sheet layout (LOY-22, master
prompt §50-51: "PrintJob integration, reprints").

Pure infra function — no domain entities, no bounded-context UoW access.
The application-layer use case resolves entities into plain `PrintUnit`
values and supplies already-resolved placeholder VALUES; this module never
reaches into Customers/Loyalty/Sales for real data itself — same
bounded-context-isolation discipline as every other cross-context piece in
this pipeline (LOY-12's `CouponDefinition.source_program_id`, LOY-16's
`LoyaltyCard.membership_id`, etc.).

Renders REAL, scannable QR codes (`qrcode`) and barcodes (`python-barcode`)
— confirmed available in this environment before writing this module, same
"check what's actually installed" discipline as LOY-19.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


@dataclass(frozen=True, slots=True)
class PrintUnit:
    """One physical card's worth of print data — `sheet_number`/
    `position_in_sheet` come from `LoyaltyCardBatchItem` (LOY-21, already
    derived, never guessed here); `placeholder_values` is fully resolved by
    the caller before this module ever sees it."""
    card_id: str
    sheet_number: int
    position_in_sheet: int
    placeholder_values: dict[str, str]


def _resolve_text(content: str, values: dict[str, str]) -> str:
    def _sub(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise InvalidCardDesignSchemaError(
                f"Falta el valor para el placeholder {{{{{key}}}}}")
        return str(values[key])
    return _PLACEHOLDER_RE.sub(_sub, content)


def _draw_qr(c: pdfcanvas.Canvas, value: str, x_pt: float, y_pt: float,
             w_pt: float, h_pt: float) -> None:
    import qrcode
    buf = BytesIO()
    qrcode.make(value).save(buf, format="PNG")
    buf.seek(0)
    c.drawImage(ImageReader(buf), x_pt, y_pt, width=w_pt, height=h_pt,
                preserveAspectRatio=True, mask="auto")


_BARCODE_WRITER_KEYS = {"CODE128": "code128", "CODE39": "code39"}


def _draw_barcode(c: pdfcanvas.Canvas, value: str, fmt: str, x_pt: float, y_pt: float,
                   w_pt: float, h_pt: float) -> None:
    import barcode
    from barcode.writer import ImageWriter
    barcode_cls = barcode.get_barcode_class(_BARCODE_WRITER_KEYS[fmt])
    buf = BytesIO()
    barcode_cls(value, writer=ImageWriter()).write(buf, options={"write_text": False})
    buf.seek(0)
    c.drawImage(ImageReader(buf), x_pt, y_pt, width=w_pt, height=h_pt,
                preserveAspectRatio=True, mask="auto")


def render_batch_pdf(
    *, sheet_width_mm: Decimal, sheet_height_mm: Decimal, margin_left_mm: Decimal,
    margin_top_mm: Decimal, columns: int, rows: int, card_width_mm: Decimal,
    card_height_mm: Decimal, bleed_mm: Decimal, gutter_horizontal_mm: Decimal,
    gutter_vertical_mm: Decimal, design_schema: dict, print_units: list[PrintUnit],
) -> bytes:
    """One page per distinct `sheet_number` present in `print_units` — a
    reprint of a single sheet is just calling this again with a
    `print_units` list filtered to that sheet, never touching the others.
    """
    if not print_units:
        raise InvalidCardDesignSchemaError("No hay unidades de impresión para renderizar")

    canvas_width_mm = Decimal(str(design_schema["canvas"]["width_mm"]))
    canvas_height_mm = Decimal(str(design_schema["canvas"]["height_mm"]))
    scale_x = card_width_mm / canvas_width_mm
    scale_y = card_height_mm / canvas_height_mm

    cell_width_mm = card_width_mm + (bleed_mm * 2)
    cell_height_mm = card_height_mm + (bleed_mm * 2)

    sheets: dict[int, list[PrintUnit]] = {}
    for unit in print_units:
        sheets.setdefault(unit.sheet_number, []).append(unit)

    buf = BytesIO()
    page_size = (float(sheet_width_mm) * mm, float(sheet_height_mm) * mm)
    c = pdfcanvas.Canvas(buf, pagesize=page_size)

    for sheet_number in sorted(sheets.keys()):
        for unit in sheets[sheet_number]:
            if not (1 <= unit.position_in_sheet <= columns * rows):
                raise InvalidCardDesignSchemaError(
                    f"position_in_sheet {unit.position_in_sheet} fuera de rango para "
                    f"{columns}x{rows}")
            col = (unit.position_in_sheet - 1) % columns
            row = (unit.position_in_sheet - 1) // columns
            cell_x_mm = margin_left_mm + col * (cell_width_mm + gutter_horizontal_mm) + bleed_mm
            # PDF y-origin is bottom-left; row 0 is the TOP row of the sheet.
            cell_y_from_top_mm = (
                margin_top_mm + row * (cell_height_mm + gutter_vertical_mm) + bleed_mm)
            cell_y_mm = sheet_height_mm - cell_y_from_top_mm - card_height_mm

            origin_x_pt = float(cell_x_mm) * mm
            origin_y_pt = float(cell_y_mm) * mm

            for element in design_schema.get("elements", []):
                ex_mm = Decimal(str(element["x_mm"])) * scale_x
                ey_top_mm = Decimal(str(element["y_mm"])) * scale_y
                ew_mm = Decimal(str(element["width_mm"])) * scale_x
                eh_mm = Decimal(str(element["height_mm"])) * scale_y
                ex_pt = origin_x_pt + float(ex_mm) * mm
                ew_pt = float(ew_mm) * mm
                eh_pt = float(eh_mm) * mm
                # element y is measured from the TOP of the card canvas.
                ey_pt = origin_y_pt + float(card_height_mm) * mm - float(ey_top_mm) * mm - eh_pt

                element_type = element["type"]
                if element_type == "TEXT":
                    text = _resolve_text(element.get("content", ""), unit.placeholder_values)
                    c.setFont("Helvetica", max(eh_pt * 0.6, 4))
                    align = element.get("align", "LEFT")
                    if align == "CENTER":
                        c.drawCentredString(ex_pt + ew_pt / 2, ey_pt, text)
                    elif align == "RIGHT":
                        c.drawRightString(ex_pt + ew_pt, ey_pt, text)
                    else:
                        c.drawString(ex_pt, ey_pt, text)
                elif element_type == "QR":
                    value = unit.placeholder_values.get("card_token")
                    if not value:
                        raise InvalidCardDesignSchemaError(
                            "Falta card_token para el elemento QR")
                    _draw_qr(c, value, ex_pt, ey_pt, ew_pt, eh_pt)
                elif element_type == "BARCODE":
                    value = unit.placeholder_values.get("card_number")
                    if not value:
                        raise InvalidCardDesignSchemaError(
                            "Falta card_number para el elemento BARCODE")
                    _draw_barcode(c, value, element["format"], ex_pt, ey_pt, ew_pt, eh_pt)
                elif element_type == "SHAPE":
                    shape_type = element["shape_type"]
                    if shape_type == "RECTANGLE":
                        c.rect(ex_pt, ey_pt, ew_pt, eh_pt, stroke=1, fill=0)
                    elif shape_type == "CIRCLE":
                        c.ellipse(ex_pt, ey_pt, ex_pt + ew_pt, ey_pt + eh_pt, stroke=1, fill=0)
                    elif shape_type == "LINE":
                        c.line(ex_pt, ey_pt, ex_pt + ew_pt, ey_pt + eh_pt)
                elif element_type == "IMAGE":
                    # No asset store wired yet (honest gap) — draws a
                    # labeled placeholder box instead of fabricating image
                    # content.
                    c.rect(ex_pt, ey_pt, ew_pt, eh_pt, stroke=1, fill=0)
                    c.setFont("Helvetica", 6)
                    c.drawCentredString(ex_pt + ew_pt / 2, ey_pt + eh_pt / 2, "[IMAGE]")
        c.showPage()

    c.save()
    return buf.getvalue()
