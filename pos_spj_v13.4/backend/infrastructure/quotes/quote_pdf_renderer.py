"""Documento PDF de una cotización (CRM-43).

Función de infraestructura pura: recibe valores ya resueltos (``QuoteDocument``)
y escribe el PDF con reportlab (mismo motor que las tarjetas de Fidelidad). No
lee la base ni conoce entidades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass(frozen=True, slots=True)
class QuoteDocumentLine:
    code: str
    description: str
    quantity: str
    unit: str
    unit_price: str
    amount: str


@dataclass(frozen=True, slots=True)
class QuoteDocument:
    company_name: str
    company_lines: tuple[str, ...]
    number: str
    issued_on: str
    valid_until: str
    customer_name: str
    customer_lines: tuple[str, ...]
    lines: tuple[QuoteDocumentLine, ...]
    list_subtotal: str
    discount_total: str
    total: str
    currency: str
    notes: str = ""
    prepared_by: str = ""
    extra: dict = field(default_factory=dict)


def render_quote_pdf(document: QuoteDocument, path: str) -> str:
    styles = getSampleStyleSheet()
    normal, title = styles["Normal"], styles["Title"]
    small = styles["BodyText"]

    def p(text: str, style=normal) -> Paragraph:
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    story = [p(document.company_name, styles["Heading2"])]
    story += [p(line, small) for line in document.company_lines if line]
    story += [Spacer(1, 4 * mm), p(f"Cotización {document.number}", title)]
    head = Table([
        [p("Cliente"), p(document.customer_name), p("Fecha"), p(document.issued_on)],
        [p(""), p("\n".join(x for x in document.customer_lines if x)), p("Válida hasta"),
         p(document.valid_until)],
    ], colWidths=[22 * mm, 88 * mm, 28 * mm, 40 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
    story += [head, Spacer(1, 5 * mm)]

    rows = [["Código", "Descripción", "Cantidad", "Precio", "Importe"]]
    rows += [[line.code, p(line.description, small), f"{line.quantity} {line.unit}".strip(),
              line.unit_price, line.amount] for line in document.lines]
    table = Table(rows, colWidths=[24 * mm, 82 * mm, 26 * mm, 23 * mm, 23 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.grey),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [table, Spacer(1, 4 * mm)]

    totals = []
    if document.discount_total not in ("", "$0.00"):
        totals += [["Subtotal a precio de lista", document.list_subtotal],
                   ["Descuento", f"-{document.discount_total}"]]
    totals += [[f"Total ({document.currency})", document.total]]
    total_table = Table(totals, colWidths=[60 * mm, 30 * mm], hAlign="RIGHT")
    total_table.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"),
                                     ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                                     ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]))
    story += [total_table, Spacer(1, 6 * mm)]
    if document.notes:
        story += [p("Condiciones y notas", styles["Heading4"]), p(document.notes, small)]
    story += [Spacer(1, 4 * mm), p(
        f"Precios sujetos a la vigencia indicada (hasta el {document.valid_until})."
        + (f" Atendió: {document.prepared_by}." if document.prepared_by else ""), small)]

    SimpleDocTemplate(path, pagesize=letter, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm,
                      title=f"Cotización {document.number}").build(story)
    return path
