"""Recibo de nómina en PDF (reportlab, el motor de cotizaciones y tarjetas) y
como ticket ESC/POS para térmicas de 58/80 mm.

Funciones de infraestructura puras: reciben ``PayrollReceipt`` ya resueltos y
producen bytes/archivos. No leen la base.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from backend.infrastructure.printing.escpos import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT_PARTIAL,
    DEFAULT_ENCODING,
    INIT,
    sanitize_text,
)


def render_payroll_receipts_pdf(receipts, path: str) -> str:
    """Una hoja carta por recibo, con firma de conformidad."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    normal, small = styles["Normal"], styles["BodyText"]

    def p(text, style=normal):
        return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)

    def concept_table(title_text, items, total):
        rows = [[title_text, "Detalle", "Importe"]]
        rows += [[line.concept, p(line.detail, small), f"${line.amount}"] for line in items]
        rows.append(["Total", "", f"${total}"])
        table = Table(rows, colWidths=[50 * mm, 92 * mm, 36 * mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
            ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return table

    story = []
    for index, receipt in enumerate(receipts):
        if index:
            story.append(PageBreak())
        story.append(p(receipt.company_name or "Recibo de nómina", styles["Heading2"]))
        if receipt.company_tax_id:
            story.append(p(f"RFC {receipt.company_tax_id}", small))
        story.append(p(f"Sucursal: {receipt.branch_name}", small))
        title = "Recibo de nómina"
        if receipt.preliminary:
            title += " — PRELIMINAR (corrida no pagada)"
        elif receipt.reprint:
            title += " — REIMPRESIÓN"
        story += [Spacer(1, 3 * mm), p(title, styles["Title"])]
        head = Table([
            [p("Folio"), p(receipt.folio), p("Periodo"),
             p(f"{receipt.period_start} al {receipt.period_end}")],
            [p("Empleado"), p(f"{receipt.employee_code} — {receipt.employee_name}"),
             p("Corrida"), p(receipt.run_type)],
            [p("RFC"), p(receipt.tax_identifier or "—"), p("Ingreso"), p(receipt.hire_date)],
            [p("Puesto"), p(receipt.position or "—"), p("Departamento"),
             p(receipt.department or "—")],
        ], colWidths=[22 * mm, 68 * mm, 30 * mm, 58 * mm])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                                  ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold")]))
        story += [head, Spacer(1, 5 * mm),
                  concept_table("Percepciones", receipt.perceptions, receipt.gross),
                  Spacer(1, 4 * mm)]
        if receipt.deductions:
            story += [concept_table("Deducciones", receipt.deductions,
                                    receipt.deductions_total), Spacer(1, 4 * mm)]
        net = Table([[f"Neto a recibir ({receipt.currency})", f"${receipt.net}"]],
                    colWidths=[70 * mm, 36 * mm], hAlign="RIGHT")
        net.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                                 ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                 ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black)]))
        story += [net, Spacer(1, 5 * mm)]
        if receipt.payment_method:
            payment = f"Pagado por {receipt.payment_method} el {receipt.paid_at}"
            if receipt.payment_reference:
                payment += f" · referencia {receipt.payment_reference}"
            story.append(p(payment, small))
        story += [Spacer(1, 22 * mm), p("_" * 48, small),
                  p(f"Recibí de conformidad — {receipt.employee_name}", small),
                  Spacer(1, 4 * mm),
                  p("Este recibo no es un comprobante fiscal (CFDI de nómina).", small)]

    first = receipts[0] if receipts else None
    SimpleDocTemplate(path, pagesize=letter, leftMargin=15 * mm, rightMargin=15 * mm,
                      topMargin=15 * mm, bottomMargin=15 * mm,
                      title=f"Recibos de nómina {first.period_start if first else ''}").build(story)
    return path


class PayrollReceiptEscPosRenderer:
    """Ticket de recibo: 32 columnas en 58 mm, 48 en 80 mm."""

    TITLE = "RECIBO DE NOMINA"

    def __init__(self, *, paper_width_mm: int = 80, encoding: str = DEFAULT_ENCODING) -> None:
        self._width = 48 if int(paper_width_mm) >= 80 else 32
        self._encoding = encoding

    def _pair(self, label: str, amount: str) -> str:
        value = f"${amount}"
        room = max(1, self._width - len(value) - 1)
        return f"{label[:room]:<{room}} {value}"

    def lines(self, receipt) -> tuple[list[str], list[str]]:
        """(encabezado antes del título, cuerpo después del título)."""
        width = self._width
        rule = "-" * width
        head = [receipt.company_name[:width].center(width)] if receipt.company_name else []
        body = []
        if receipt.preliminary:
            body.append("*** PRELIMINAR - NO PAGADA ***".center(width))
        elif receipt.reprint:
            body.append("*** REIMPRESION ***".center(width))
        body += [rule, f"Folio: {receipt.folio}", f"Sucursal: {receipt.branch_name}",
                 f"Periodo: {receipt.period_start} a {receipt.period_end}",
                 f"Empleado: {receipt.employee_code}", receipt.employee_name[:width],
                 rule, "PERCEPCIONES"]
        body += [self._pair(line.concept, line.amount) for line in receipt.perceptions]
        body.append(self._pair("Total percepciones", receipt.gross))
        if receipt.deductions:
            body += [rule, "DEDUCCIONES"]
            body += [self._pair(line.concept, line.amount) for line in receipt.deductions]
            body.append(self._pair("Total deducciones", receipt.deductions_total))
        body += [rule, self._pair("NETO A RECIBIR", receipt.net)]
        if receipt.payment_method:
            body.append(f"Pago: {receipt.payment_method} {receipt.paid_at}")
            if receipt.payment_reference:
                body.append(f"Ref: {receipt.payment_reference}")
        body += ["", "", "_" * min(width, 32), "Recibi de conformidad"]
        return head, [part for line in body for part in self._wrap(line)]

    def _wrap(self, line: str) -> list[str]:
        if len(line) <= self._width:
            return [line]
        return [line[i:i + self._width] for i in range(0, len(line), self._width)]

    def text(self, receipt) -> str:
        head, body = self.lines(receipt)
        return "\n".join(sanitize_text(line, encoding=self._encoding)
                         for line in [*head, self.TITLE.center(self._width), *body])

    def render(self, receipts) -> bytes:
        def encode(lines) -> bytes:
            text = "\n".join(sanitize_text(line, encoding=self._encoding) for line in lines)
            return (text + "\n").encode(self._encoding, errors="replace") if text else b""

        chunks = []
        for receipt in receipts:
            head, body = self.lines(receipt)
            chunks.append(INIT + ALIGN_LEFT + encode(head) + ALIGN_CENTER + BOLD_ON
                          + self.TITLE.encode(self._encoding) + b"\n" + BOLD_OFF + ALIGN_LEFT
                          + encode(body) + b"\n\n\n" + CUT_PARTIAL)
        return b"".join(chunks)
