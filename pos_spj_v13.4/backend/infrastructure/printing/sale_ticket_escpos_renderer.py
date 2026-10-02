"""Ticket de venta en ESC/POS para impresoras térmicas.

POR QUÉ EXISTE (re-auditoría POS, 2026-10-01)
---------------------------------------------
El ticket de venta lo imprimía `core/services/printer_service.py::PrinterService`
con `core/ticket_escpos_renderer.py`. Ambos se fueron con la carpeta `core/` y
nada los reemplazó para Ventas: el shell construía el POS con
`printer_service=None`, así que **el POS no imprimía ningún ticket** y
"Reimprimir" llamaba a un método de `None`. No se recuperó nada del historial
(§18): se escribe sobre los comandos públicos de `escpos.py`.

Recibe el MISMO diccionario que `SalesReceiptClient._to_ticket_payload` ya
compone (folio, fecha, cajero, cliente, renglones, totales, pago, fidelidad,
mensajes) más un encabezado opcional (empresa, sucursal, dirección, teléfono,
pie). No decide nada de negocio: presenta lo que Ventas ya calculó.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.infrastructure.printing.escpos import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT_PARTIAL,
    DEFAULT_ENCODING,
    FEED_LINE,
    INIT,
    sanitize_text,
)

#: Los códigos canónicos de pago (§31) en el idioma del ticket.
PAYMENT_LABELS = {
    "CASH": "Efectivo", "CARD": "Tarjeta", "TRANSFER": "Transferencia",
    "CREDIT": "Credito", "MERCADO_PAGO": "Mercado Pago", "Mixto": "Mixto",
}

#: Caracteres por renglón con la fuente A estándar.
COLUMNS_BY_PAPER_WIDTH_MM = {58: 32, 80: 48}


def _money(value: Any) -> str:
    try:
        return f"${Decimal(str(value or 0)):,.2f}"
    except (InvalidOperation, ValueError):
        return "$0.00"


def _quantity(value: Any) -> str:
    try:
        cantidad = Decimal(str(value or 0)).normalize()
    except (InvalidOperation, ValueError):
        return "0"
    return format(cantidad, "f")


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
    espacio = max(1, width - len(label) - len(value))
    return f"{label}{' ' * espacio}{value}"


def render_sale_ticket(payload: dict[str, Any], *, header: dict[str, Any] | None = None,
                       paper_width_mm: int = 80, encoding: str = DEFAULT_ENCODING) -> bytes:
    width = COLUMNS_BY_PAPER_WIDTH_MM.get(int(paper_width_mm or 80), 48)
    header = header or {}
    out = bytearray(INIT)

    def line(text: str = "") -> None:
        out.extend(sanitize_text(text, encoding=encoding).encode(encoding, errors="replace"))
        out.extend(FEED_LINE)

    rule = "-" * width
    out.extend(ALIGN_CENTER)
    nombre = header.get("company_name") or ""
    if nombre:
        out.extend(BOLD_ON)
        for renglon in _wrap(nombre, width):
            line(renglon)
        out.extend(BOLD_OFF)
    for clave in ("branch_name", "address", "phone", "header_text"):
        if header.get(clave):
            for renglon in _wrap(str(header[clave]), width):
                line(renglon)
    out.extend(ALIGN_LEFT)
    line(rule)
    if payload.get("reimpresion"):
        out.extend(ALIGN_CENTER + BOLD_ON)
        line("*** REIMPRESION ***")
        out.extend(BOLD_OFF + ALIGN_LEFT)
    line(_pair("Folio:", str(payload.get("folio") or ""), width))
    line(_pair("Fecha:", str(payload.get("fecha") or "")[:19].replace("T", " "), width))
    line(_pair("Cajero:", str(payload.get("cajero") or ""), width))
    line(_pair("Cliente:", str(payload.get("cliente") or "Publico General")[: width - 9], width))
    line(rule)

    for item in payload.get("items") or ():
        for renglon in _wrap(str(item.get("nombre") or ""), width):
            line(renglon)
        detalle = (f"  {_quantity(item.get('cantidad'))} {item.get('unidad') or ''}"
                   f" x {_money(item.get('precio_unitario'))}")
        line(_pair(detalle, _money(item.get("total")), width))
    line(rule)

    totales = payload.get("totales") or {}
    line(_pair("Subtotal", _money(totales.get("subtotal")), width))
    if Decimal(str(totales.get("descuento") or 0)) > 0:
        line(_pair("Descuento", "-" + _money(totales.get("descuento")), width))
    if Decimal(str(totales.get("impuestos") or 0)) > 0:
        line(_pair("Impuestos", _money(totales.get("impuestos")), width))
    out.extend(BOLD_ON)
    line(_pair("TOTAL", _money(totales.get("total_final")), width))
    out.extend(BOLD_OFF)

    pago = payload.get("pago") or {}
    if pago.get("forma_pago"):
        forma = str(pago["forma_pago"])
        line(_pair("Forma de pago", PAYMENT_LABELS.get(forma, forma), width))
    if Decimal(str(pago.get("efectivo_recibido") or 0)) > 0:
        line(_pair("Efectivo recibido", _money(pago.get("efectivo_recibido")), width))
        line(_pair("Cambio", _money(pago.get("cambio")), width))

    fidelidad = payload.get("loyalty") or {}
    if fidelidad.get("available") or fidelidad.get("puntos_totales"):
        line(rule)
        if fidelidad.get("puntos_ganados") is not None:
            line(_pair("Puntos ganados", str(fidelidad["puntos_ganados"]), width))
        line(_pair("Puntos acumulados", str(fidelidad.get("puntos_totales") or 0), width))
        if fidelidad.get("nivel"):
            line(_pair("Nivel", str(fidelidad["nivel"]), width))

    mensajes = list(payload.get("fomo_messages") or ())
    if mensajes or header.get("footer_text"):
        line(rule)
        out.extend(ALIGN_CENTER)
        for mensaje in mensajes:
            for renglon in _wrap(str(mensaje), width):
                line(renglon)
        if header.get("footer_text"):
            for renglon in _wrap(str(header["footer_text"]), width):
                line(renglon)
        out.extend(ALIGN_LEFT)

    out.extend(ALIGN_CENTER)
    line("Gracias por su compra")
    out.extend(ALIGN_LEFT)
    out.extend(FEED_LINE * 4)
    out.extend(CUT_PARTIAL)
    return bytes(out)
