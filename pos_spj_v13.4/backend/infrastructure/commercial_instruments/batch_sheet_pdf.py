"""Pliego en PDF de un lote de cupones o vales (auditoría de Fidelidad 968e0bc).

Carta, 2 columnas × 5 filas (10 piezas por hoja), cada pieza con:
nombre del lote, valor, folio, vigencia, el código legible y su Code 128.
Línea punteada de corte entre piezas. El motor es reportlab, el mismo de
cotizaciones, tarjetas y recibos de nómina.

El código completo sólo existe mientras se genera este archivo: no se guarda.
"""

from __future__ import annotations

from decimal import Decimal

_COLUMNS, _ROWS = 2, 5


def render_batch_sheet_pdf(pieces, path: str, *, batch_name: str) -> str:
    from reportlab.graphics.barcode import code128
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    ancho_hoja, alto_hoja = letter
    margen = 10 * mm
    ancho = (ancho_hoja - 2 * margen) / _COLUMNS
    alto = (alto_hoja - 2 * margen) / _ROWS
    hoja = canvas.Canvas(path, pagesize=letter)
    hoja.setTitle(f"Lote {batch_name}")
    por_hoja = _COLUMNS * _ROWS
    for indice, pieza in enumerate(pieces):
        if indice and indice % por_hoja == 0:
            hoja.showPage()
        lugar = indice % por_hoja
        x = margen + (lugar % _COLUMNS) * ancho
        y = alto_hoja - margen - (lugar // _COLUMNS + 1) * alto
        hoja.setDash(2, 3)
        hoja.rect(x, y, ancho, alto)
        hoja.setDash()
        tipo = "CUPÓN" if pieza.kind == "COUPON" else "VALE"
        hoja.setFont("Helvetica-Bold", 12)
        hoja.drawString(x + 6 * mm, y + alto - 9 * mm, f"{tipo} · {batch_name}"[:48])
        hoja.setFont("Helvetica-Bold", 18)
        valor = Decimal(str(pieza.value))
        hoja.drawString(x + 6 * mm, y + alto - 18 * mm, f"$ {valor:,.2f}")
        hoja.setFont("Helvetica", 8)
        vigencia = f"Válido hasta {pieza.valid_to[:10]}" if pieza.valid_to else "Sin vencimiento"
        hoja.drawString(x + 6 * mm, y + alto - 23 * mm, f"Folio {pieza.folio} · {vigencia}")
        barras = code128.Code128(pieza.code.replace("-", ""), barHeight=12 * mm,
                                 barWidth=0.33 * mm)
        barras.drawOn(hoja, x + (ancho - barras.width) / 2, y + 10 * mm)
        hoja.setFont("Courier-Bold", 10)
        hoja.drawCentredString(x + ancho / 2, y + 5 * mm, pieza.code)
    hoja.save()
    return path


__all__ = ["render_batch_sheet_pdf"]
