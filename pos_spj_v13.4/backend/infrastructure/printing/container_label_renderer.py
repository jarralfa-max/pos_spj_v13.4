"""Dibujo de la etiqueta de contenedor (2026-10-17): PDF, vista previa y ESC/POS.

Un solo diseño para los tres destinos, a partir de `ContainerLabelContent`:

* PDF de una etiqueta por página (100 × 50 o 50 × 30 mm): se imprime por el
  controlador de Windows de cualquier impresora de etiquetas.
* PDF en hoja carta con 10 etiquetas de 101.6 × 50.8 mm (2 × 5).
* ESC/POS para la impresora térmica de tickets.

El QR se dibuja como VECTORES (nítido a cualquier tamaño), con corrección de
errores M y la zona de silencio de 4 módulos que exigen los lectores de
teléfono. El lado mínimo del QR es 22 mm: una cámara lo lee a ~30 cm.
"""

from __future__ import annotations

from io import BytesIO

from backend.domain.logistics.labels import ContainerLabelContent, ContainerLabelFormat

_MM_PER_PT = 25.4 / 72

#: (ancho, alto) en mm de UNA etiqueta.
LABEL_SIZE_MM = {
    ContainerLabelFormat.LABEL_100X50: (100.0, 50.0),
    ContainerLabelFormat.LABEL_50X30: (50.0, 30.0),
    ContainerLabelFormat.SHEET_LETTER_2X5: (101.6, 50.8),
}
#: Hoja carta tipo 5163: márgenes y separación en mm.
_SHEET = {"page": (215.9, 279.4), "cols": 2, "rows": 5, "left": 3.97, "top": 12.7,
          "gutter_x": 4.76, "gutter_y": 0.0}


def qr_matrix(payload: str) -> list[list[bool]]:
    """Módulos del QR con su zona de silencio (4 módulos por lado)."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=4, box_size=1)
    code.add_data(payload)
    code.make(fit=True)
    return code.get_matrix()


def _lines(content: ContainerLabelContent) -> list[str]:
    detalle = f"Tara {content.tare_weight} kg"
    if content.capacity_weight:
        detalle += f" · Cap. {content.capacity_weight} kg"
    lineas = [content.type_name or content.category_label, detalle]
    if content.owner_name:
        lineas.append(f"Propiedad de {content.owner_name}")
    return lineas


# ── PDF ──────────────────────────────────────────────────────────────────────
def _draw_qr_pdf(c, payload: str, x_mm: float, y_mm: float, side_mm: float) -> None:
    from reportlab.lib.units import mm

    matrix = qr_matrix(payload)
    n = len(matrix)
    module = side_mm / n
    c.setFillColorRGB(0, 0, 0)
    for row, cells in enumerate(matrix):
        for col, dark in enumerate(cells):
            if dark:
                c.rect((x_mm + col * module) * mm, (y_mm + (n - 1 - row) * module) * mm,
                       module * mm + 0.05, module * mm + 0.05, stroke=0, fill=1)


def _fit_font(c, text: str, font: str, max_size: float, width_mm: float) -> float:
    from reportlab.lib.units import mm

    size = max_size
    while size > 5 and c.stringWidth(text, font, size) > width_mm * mm:
        size -= 0.5
    return size


def _draw_label_pdf(c, content: ContainerLabelContent, x_mm: float, y_mm: float,
                    w_mm: float, h_mm: float) -> None:
    """Una etiqueta con su esquina inferior izquierda en (x, y)."""
    from reportlab.lib.units import mm

    margen = 2.0 if h_mm < 40 else 3.0
    lado = h_mm - 2 * margen
    _draw_qr_pdf(c, content.qr_payload, x_mm + margen, y_mm + margen, lado)
    texto_x = x_mm + margen + lado + 1.5
    ancho = w_mm - (texto_x - x_mm) - margen
    tope = y_mm + h_mm - margen
    codigo = content.code
    talla = _fit_font(c, codigo, "Helvetica-Bold", 30 if h_mm >= 40 else 14, ancho)
    c.setFont("Helvetica-Bold", talla)
    tope -= talla * _MM_PER_PT
    c.drawString(texto_x * mm, tope * mm, codigo)
    menor = 9 if h_mm >= 40 else 5.5
    for linea in _lines(content) if h_mm >= 40 else _lines(content)[:2]:
        talla_l = _fit_font(c, linea, "Helvetica", menor, ancho)
        c.setFont("Helvetica", talla_l)
        tope -= talla_l * _MM_PER_PT * 1.35
        c.drawString(texto_x * mm, tope * mm, linea)
    if h_mm >= 40:
        c.setFont("Helvetica", 6.5)
        c.drawString(texto_x * mm, (y_mm + margen) * mm,
                     f"Escanea con la app de Logística · QR v{content.qr_version}")


def render_pdf(contents: list[ContainerLabelContent], fmt: ContainerLabelFormat,
               *, copies: int = 1) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas

    if not fmt.is_pdf:
        raise ValueError("Ese formato no es PDF")
    etiquetas = [item for item in contents for _ in range(max(1, int(copies or 1)))]
    if not etiquetas:
        raise ValueError("No hay etiquetas que generar")
    buffer = BytesIO()
    w, h = LABEL_SIZE_MM[fmt]
    if fmt is ContainerLabelFormat.SHEET_LETTER_2X5:
        page_w, page_h = _SHEET["page"]
        c = pdfcanvas.Canvas(buffer, pagesize=(page_w * mm, page_h * mm))
        por_hoja = _SHEET["cols"] * _SHEET["rows"]
        for index, content in enumerate(etiquetas):
            if index and index % por_hoja == 0:
                c.showPage()
            pos = index % por_hoja
            fila, col = divmod(pos, _SHEET["cols"])
            x = _SHEET["left"] + col * (w + _SHEET["gutter_x"])
            y = page_h - _SHEET["top"] - (fila + 1) * h - fila * _SHEET["gutter_y"]
            _draw_label_pdf(c, content, x, y, w, h)
    else:
        c = pdfcanvas.Canvas(buffer, pagesize=(w * mm, h * mm))
        for index, content in enumerate(etiquetas):
            if index:
                c.showPage()
            _draw_label_pdf(c, content, 0, 0, w, h)
    c.setTitle("Etiquetas de contenedor")
    c.save()
    return buffer.getvalue()


# ── vista previa (PNG) ──────────────────────────────────────────────────────
def _font(size_px: int, bold: bool = False):
    from PIL import ImageFont

    for nombre in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold
                   else ("arial.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(nombre, size_px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size_px)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def render_preview_png(content: ContainerLabelContent, fmt: ContainerLabelFormat,
                       *, px_per_mm: int = 8) -> bytes:
    """La misma composición que el PDF, como imagen para la pantalla."""
    from PIL import Image, ImageDraw

    w, h = LABEL_SIZE_MM.get(fmt, (100.0, 50.0))
    W, H = int(w * px_per_mm), int(h * px_per_mm)
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W - 1, H - 1], outline=(180, 180, 180))
    margen = (2.0 if h < 40 else 3.0) * px_per_mm
    lado = H - 2 * margen
    matrix = qr_matrix(content.qr_payload)
    # Módulos de píxeles ENTEROS: con anchos fraccionarios la imagen queda con
    # módulos desparejos y un lector la puede rechazar.
    modulo = max(1, int(lado // len(matrix)))
    origen = margen + (lado - modulo * len(matrix)) / 2
    origen = int(origen)
    for fila, celdas in enumerate(matrix):
        for col, oscuro in enumerate(celdas):
            if oscuro:
                x0, y0 = origen + col * modulo, origen + fila * modulo
                draw.rectangle([x0, y0, x0 + modulo - 1, y0 + modulo - 1], fill="black")
    x = margen + lado + 1.5 * px_per_mm
    ancho = W - x - margen
    y = margen
    talla = int((30 if h >= 40 else 14) * _MM_PER_PT * px_per_mm)
    fuente = _font(talla, bold=True)
    while talla > 8 and draw.textlength(content.code, font=fuente) > ancho:
        talla -= 2
        fuente = _font(talla, bold=True)
    draw.text((x, y), content.code, fill="black", font=fuente)
    y += talla * 1.15
    menor = int((9 if h >= 40 else 5.5) * _MM_PER_PT * px_per_mm)
    for linea in _lines(content) if h >= 40 else _lines(content)[:2]:
        draw.text((x, y), linea, fill="black", font=_font(menor))
        y += menor * 1.35
    salida = BytesIO()
    img.save(salida, format="PNG")
    return salida.getvalue()


# ── ESC/POS ─────────────────────────────────────────────────────────────────
_INIT, _CENTER = b"\x1b@", b"\x1ba\x01"
_BOLD_ON, _BOLD_OFF = b"\x1bE\x01", b"\x1bE\x00"
_DOUBLE, _NORMAL = b"\x1d!\x11", b"\x1d!\x00"
_CUT = b"\x1dV\x41\x03"


def render_escpos(content: ContainerLabelContent, *, paper_mm: int, copies: int = 1) -> bytes:
    from backend.infrastructure.printing.escpos import (
        dots_for_paper_width,
        render_qr,
        sanitize_text,
    )

    def texto(value: str) -> bytes:
        return sanitize_text(value).encode("cp437", "replace")

    cuerpo = (_INIT + _CENTER + render_qr(content.qr_payload,
                                          max_width_dots=dots_for_paper_width(paper_mm))
              + b"\n" + _BOLD_ON + _DOUBLE + texto(content.code) + _NORMAL + _BOLD_OFF + b"\n")
    for linea in _lines(content):
        cuerpo += texto(linea) + b"\n"
    cuerpo += b"\n\n\n" + _CUT
    return cuerpo * max(1, int(copies or 1))


class ReportlabContainerLabelRenderer:
    """Implementación del puerto `ContainerLabelRenderer` de Logística."""

    def pdf(self, contents, fmt, *, copies: int = 1) -> bytes:
        return render_pdf(list(contents), ContainerLabelFormat(fmt), copies=copies)

    def preview_png(self, content, fmt) -> bytes:
        return render_preview_png(content, ContainerLabelFormat(fmt))
