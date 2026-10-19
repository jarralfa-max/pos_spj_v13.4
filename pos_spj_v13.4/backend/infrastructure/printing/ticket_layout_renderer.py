"""Renderizador ESC/POS del ticket por bloques (comparativa main ↔ ERP, 2026-10-16).

Recorre `TicketLayout` (el contenido de la versión ACTIVA de la plantilla) y
compone los bytes bloque por bloque: logo rasterizado, encabezado, renglones,
totales, fidelidad, mensajes, código de barras del folio y QR. La vista previa
del diseñador interpreta ESTOS bytes (`escpos_preview`): lo que se ve es lo que
sale.

Lo gráfico nunca tumba el ticket: si el logo, el código o el QR no se pueden
generar (archivo ausente, librería que falta, dato que la simbología no admite),
se imprime un texto de respaldo y se devuelve el motivo en `warnings` — la
pantalla lo muestra en vez de imprimir en silencio un ticket incompleto.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.domain.document_output.ticket_layout import (
    TicketLayout,
    default_layout,
    fill_qr_url,
)
from backend.infrastructure.printing.escpos import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    BOLD_OFF,
    BOLD_ON,
    CUT_PARTIAL,
    DEFAULT_ENCODING,
    FEED_LINE,
    INIT,
    dots_for_paper_width,
    raster_image,
    render_barcode,
    render_qr,
    sanitize_text,
)

logger = logging.getLogger("spj.printing.ticket")

PAYMENT_LABELS = {
    "CASH": "Efectivo", "CARD": "Tarjeta", "TRANSFER": "Transferencia",
    "CREDIT": "Credito", "MERCADO_PAGO": "Mercado Pago", "VOUCHER": "Vale", "Mixto": "Mixto",
}
COLUMNS_BY_PAPER_WIDTH_MM = {58: 32, 80: 48}
_ALIGN = {"left": ALIGN_LEFT, "center": ALIGN_CENTER, "right": ALIGN_RIGHT}


@dataclass
class RenderedTicket:
    data: bytes
    warnings: list[str] = field(default_factory=list)
    paper_width_mm: int = 80


def _money(value: Any) -> str:
    try:
        return f"${Decimal(str(value or 0)):,.2f}"
    except (InvalidOperation, ValueError):
        return "$0.00"


def _quantity(value: Any) -> str:
    try:
        return format(Decimal(str(value or 0)).normalize(), "f")
    except (InvalidOperation, ValueError):
        return "0"


def _wrap(text: str, width: int) -> list[str]:
    palabras, renglones, actual = str(text or "").split(), [], ""
    for palabra in palabras:
        while len(palabra) > width:
            if actual:
                renglones.append(actual)
                actual = ""
            renglones.append(palabra[:width])
            palabra = palabra[width:]
        candidato = f"{actual} {palabra}".strip()
        if len(candidato) > width:
            renglones.append(actual)
            actual = palabra
        else:
            actual = candidato
    if actual:
        renglones.append(actual)
    return renglones or [""]


def _pair(label: str, value: str, width: int) -> str:
    return f"{label}{' ' * max(1, width - len(label) - len(value))}{value}"


def resolve_paper_width(layout: TicketLayout, device_paper_mm: int | None) -> int:
    if layout.paper in ("58", "80"):
        return int(layout.paper)
    return int(device_paper_mm or 80) if int(device_paper_mm or 80) in (58, 80) else 80


def render_ticket(layout: TicketLayout, payload: dict[str, Any], *,
                  header: dict[str, Any] | None = None, paper_width_mm: int | None = 80,
                  logo_path: str | None = None, encoding: str = DEFAULT_ENCODING
                  ) -> RenderedTicket:
    paper = resolve_paper_width(layout, paper_width_mm)
    width = COLUMNS_BY_PAPER_WIDTH_MM[paper]
    dots = dots_for_paper_width(paper)
    header = header or {}
    out = bytearray(INIT)
    warnings: list[str] = []
    rule = "-" * width

    def line(text: str = "") -> None:
        out.extend(sanitize_text(text, encoding=encoding).encode(encoding, errors="replace"))
        out.extend(FEED_LINE)

    def text_block(texts, align: str, *, bold: bool = False) -> None:
        texts = [t for t in texts if str(t or "").strip()]
        if not texts:
            return
        out.extend(_ALIGN.get(align, ALIGN_CENTER))
        if bold:
            out.extend(BOLD_ON)
        for text in texts:
            for renglon in _wrap(str(text), width):
                line(renglon)
        if bold:
            out.extend(BOLD_OFF)
        out.extend(ALIGN_LEFT)

    def graphic(data: bytes, align: str) -> None:
        out.extend(_ALIGN.get(align, ALIGN_CENTER))
        out.extend(data)
        out.extend(FEED_LINE)
        out.extend(ALIGN_LEFT)

    renderers = _SALE if layout.kind == "SALE" else _RAFFLE
    for block in layout.enabled_blocks():
        handler = renderers.get(block.type)
        if handler is not None:
            handler(block, payload, header, width, dots, rule, line, text_block, graphic,
                    warnings, logo_path, out)

    out.extend(FEED_LINE * layout.feed_lines)
    if layout.cut:
        out.extend(CUT_PARTIAL)
    for warning in warnings:
        logger.warning("Ticket %s: %s", payload.get("folio") or "", warning)
    return RenderedTicket(bytes(out), warnings, paper)


# ── bloques comunes ──────────────────────────────────────────────────────
def _logo(block, payload, header, width, dots, rule, line, text_block, graphic, warnings,
          logo_path, out):
    if not logo_path:
        warnings.append("No hay logo cargado (Configuración → Empresa y sucursales)")
        return
    try:
        from PIL import Image
        with Image.open(logo_path) as image:
            image.load()
            target = max(64, int(dots * float(block.option("width_pct", 60)) / 100))
            data = raster_image(_flatten(image), max_width_dots=target)
    except Exception as exc:  # noqa: BLE001 - el ticket sale sin logo, con aviso
        warnings.append(f"El logo no se pudo imprimir: {exc}")
        return
    if not data:
        warnings.append("El logo no se pudo rasterizar (falta la librería de imágenes)")
        return
    graphic(data, block.align)


def _flatten(image):
    """Transparencia sobre blanco: en térmica lo transparente es papel."""
    from PIL import Image
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        base = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        base.alpha_composite(rgba)
        return base.convert("L")
    return image.convert("L")


def _company(block, payload, header, width, *rest):
    text_block = rest[3]
    text_block([header.get("company_name")], block.align, bold=True)


def _branch(block, payload, header, width, *rest):
    text_block = rest[3]
    text_block([header.get("branch_name"), header.get("address"), header.get("phone")],
               block.align)


def _header_text(block, payload, header, width, *rest):
    rest[3]([header.get("header_text")], block.align)


def _footer_text(block, payload, header, width, *rest):
    rest[3]([header.get("footer_text")], block.align)


def _barcode(block, payload, header, width, dots, rule, line, text_block, graphic, warnings,
             logo_path, out):
    folio = str(payload.get("folio") or "").strip()
    if not folio:
        return
    data = render_barcode(folio, max_width_dots=int(dots * 0.9), module_height=7.0)
    if data:
        graphic(data, block.align)
        text_block([folio], block.align)
    else:
        warnings.append("El código de barras no se pudo generar; se imprimió el folio")
        text_block([f"Folio: {folio}"], block.align, bold=True)


def _qr(block, payload, header, width, dots, rule, line, text_block, graphic, warnings,
        logo_path, out):
    url = str(block.option("url", "") or "").strip()
    if not url:
        return
    totales = payload.get("totales") or {}
    content = fill_qr_url(url, {
        "folio": payload.get("folio") or "", "sucursal": header.get("branch_name") or "",
        "fecha": str(payload.get("fecha") or "")[:10],
        "total": str(totales.get("total_final") or ""),
    })
    data = render_qr(content, max_width_dots=int(dots * 0.6))
    if data:
        graphic(data, block.align)
        if block.option("caption"):
            text_block([block.option("caption")], block.align)
    else:
        warnings.append("El QR no se pudo generar; se imprimió la dirección")
        text_block([content], block.align)


# ── venta ────────────────────────────────────────────────────────────────
def _sale_info(block, payload, header, width, dots, rule, line, text_block, *rest):
    line(rule)
    if payload.get("reimpresion"):
        text_block(["*** REIMPRESION ***"], "center", bold=True)
    line(_pair("Folio:", str(payload.get("folio") or ""), width))
    line(_pair("Fecha:", str(payload.get("fecha") or "")[:19].replace("T", " "), width))
    line(_pair("Cajero:", str(payload.get("cajero") or ""), width))
    line(_pair("Cliente:", str(payload.get("cliente") or "Publico General")[: width - 9], width))
    line(rule)


def _items(block, payload, header, width, dots, rule, line, *rest):
    unit_price = bool(block.option("show_unit_price", True))
    for item in payload.get("items") or ():
        for renglon in _wrap(str(item.get("nombre") or ""), width):
            line(renglon)
        detalle = f"  {_quantity(item.get('cantidad'))} {item.get('unidad') or ''}"
        if unit_price:
            detalle += f" x {_money(item.get('precio_unitario'))}"
        line(_pair(detalle, _money(item.get("total")), width))
    line(rule)


def _totals(block, payload, header, width, dots, rule, line, text_block, graphic, warnings,
            logo_path, out):
    totales = payload.get("totales") or {}
    line(_pair("Subtotal", _money(totales.get("subtotal")), width))
    if Decimal(str(totales.get("descuento") or 0)) > 0:
        line(_pair("Descuento", "-" + _money(totales.get("descuento")), width))
    if Decimal(str(totales.get("impuestos") or 0)) > 0:
        line(_pair("Impuestos", _money(totales.get("impuestos")), width))
    out.extend(BOLD_ON)
    line(_pair("TOTAL", _money(totales.get("total_final")), width))
    out.extend(BOLD_OFF)


def _payment(block, payload, header, width, dots, rule, line, *rest):
    pago = payload.get("pago") or {}
    if pago.get("forma_pago"):
        forma = str(pago["forma_pago"])
        line(_pair("Forma de pago", PAYMENT_LABELS.get(forma, forma), width))
    if Decimal(str(pago.get("efectivo_recibido") or 0)) > 0:
        line(_pair("Efectivo recibido", _money(pago.get("efectivo_recibido")), width))
        line(_pair("Cambio", _money(pago.get("cambio")), width))


def _loyalty(block, payload, header, width, dots, rule, line, *rest):
    fidelidad = payload.get("loyalty") or {}
    if not (fidelidad.get("available") or fidelidad.get("puntos_totales")):
        return
    line(rule)
    if fidelidad.get("puntos_ganados") is not None:
        line(_pair("Puntos ganados", str(fidelidad["puntos_ganados"]), width))
    line(_pair("Puntos acumulados", str(fidelidad.get("puntos_totales") or 0), width))
    if fidelidad.get("nivel"):
        line(_pair("Nivel", str(fidelidad["nivel"]), width))


def _messages(block, payload, header, width, dots, rule, line, text_block, *rest):
    mensajes = list(payload.get("fomo_messages") or ())
    if mensajes:
        line(rule)
        text_block(mensajes, block.align)


def _thanks(block, payload, header, width, dots, rule, line, text_block, *rest):
    text_block([block.option("text", "Gracias por su compra")], block.align)


# ── boleto de sorteo ─────────────────────────────────────────────────────
def _raffle_title(block, payload, header, width, dots, rule, line, text_block, *rest):
    line(rule)
    text_block([block.option("text") or "BOLETO DE SORTEO"], block.align, bold=True)
    text_block([payload.get("raffle_name")], block.align, bold=True)


def _ticket_number(block, payload, header, width, dots, rule, line, text_block, graphic,
                   warnings, logo_path, out):
    numero = str(payload.get("ticket_number") or "").strip()
    out.extend(_ALIGN.get(block.align, ALIGN_CENTER))
    out.extend(b"\x1d!\x11")          # GS ! — doble alto y ancho
    line(numero or "(sin número)")
    out.extend(b"\x1d!\x00")
    out.extend(ALIGN_LEFT)


def _customer(block, payload, header, width, dots, rule, line, text_block, *rest):
    if payload.get("cliente"):
        text_block([f"Cliente: {payload['cliente']}"], block.align)


def _prize(block, payload, header, width, dots, rule, line, text_block, *rest):
    if payload.get("prize"):
        text_block([f"Premio: {payload['prize']}"], block.align)


def _draw_date(block, payload, header, width, dots, rule, line, text_block, *rest):
    if payload.get("draw_date"):
        text_block([f"Sorteo: {str(payload['draw_date'])[:16].replace('T', ' ')}"], block.align)


def _sale_reference(block, payload, header, width, dots, rule, line, text_block, *rest):
    if payload.get("sale_folio"):
        text_block([f"Venta: {payload['sale_folio']}"], block.align)


def _legal_text(block, payload, header, width, dots, rule, line, text_block, *rest):
    if block.option("text"):
        line(rule)
        text_block([block.option("text")], block.align)


def _raffle_barcode(block, payload, *rest):
    _barcode(block, {"folio": payload.get("ticket_number")}, *rest)


def _raffle_qr(block, payload, *rest):
    _qr(block, {**payload, "folio": payload.get("ticket_number")}, *rest)


_SALE = {
    "logo": _logo, "company": _company, "branch": _branch, "header_text": _header_text,
    "sale_info": _sale_info, "items": _items, "totals": _totals, "payment": _payment,
    "loyalty": _loyalty, "messages": _messages, "footer_text": _footer_text,
    "barcode": _barcode, "qr": _qr, "thanks": _thanks,
}
_RAFFLE = {
    "logo": _logo, "company": _company, "branch": _branch, "raffle_title": _raffle_title,
    "ticket_number": _ticket_number, "customer": _customer, "prize": _prize,
    "draw_date": _draw_date, "sale_reference": _sale_reference, "barcode": _raffle_barcode,
    "qr": _raffle_qr, "legal_text": _legal_text, "footer_text": _footer_text,
}


def render_default_sale_ticket(payload: dict[str, Any], *, header: dict | None = None,
                               paper_width_mm: int = 80) -> bytes:
    return render_ticket(default_layout("SALE"), payload, header=header,
                         paper_width_mm=paper_width_mm).data
