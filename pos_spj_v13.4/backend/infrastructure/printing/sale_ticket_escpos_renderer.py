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
    """El ticket con el DISEÑO POR OMISIÓN (el de siempre). Desde 2026-10-16 el
    impresor de Ventas usa `ticket_layout_renderer.render_ticket` con el diseño de
    la versión ACTIVA de la plantilla; esto queda para quien no tenga plantilla."""
    from backend.domain.document_output.ticket_layout import default_layout
    from backend.infrastructure.printing.ticket_layout_renderer import render_ticket

    return render_ticket(default_layout("SALE"), payload, header=header,
                         paper_width_mm=paper_width_mm, encoding=encoding).data
