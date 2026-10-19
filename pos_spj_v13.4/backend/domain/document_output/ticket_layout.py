"""Diseño del ticket por bloques — el contenido REAL de una plantilla de ticket.

POR QUÉ (comparativa de tickets main ↔ ERP, 2026-10-16)
------------------------------------------------------
`main` imprimía con un diseño por bloques (logo, QR, barras, fidelidad, FOMO,
orden y visibilidad) guardado en `ticket_layouts`. En la rama ERP el impresor de
Ventas usaba un renderizador FIJO y la versión ACTIVA de `SALE_TICKET` sólo se
anotaba en el `PrintJob`: editar o activar una plantilla en Configuración no
cambiaba nada del papel. En la base real había una versión con el texto libre
«Productos, unidad, cantidad, costo» esperando aprobación — alguien intentó
diseñar el ticket y eso nunca habría llegado a la impresora.

Ahora el contenido de una versión de plantilla de ticket (`SALE_TICKET`,
`SWEEPSTAKES_TICKET`) ES este diseño, serializado en JSON. El renderizador lo
recorre bloque por bloque; la vista previa usa los mismos bytes.

Reglas (puras, sin I/O):

* tipos de bloque conocidos, cada uno a lo más una vez;
* el QR sólo lleva una URL http(s) capturada en la plantilla, con marcadores
  públicos ({folio}, {sucursal}, {fecha}, {total}); nunca datos del cliente
  (decisión del usuario: «URL configurable con folio»; sin URL no se imprime);
* el código de barras lleva el FOLIO comercial (nunca el id interno);
* máximos de mensajes por categoría (lo que antes estaba fijo en código).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable

from backend.domain.document_output.exceptions import DocumentInvalidValueError

SCHEMA = "ticket_layout/1"

ALIGNMENTS = ("left", "center", "right")
PAPER_CHOICES = ("AUTO", "58", "80")

#: Bloques del ticket de VENTA, en el orden por omisión (el de hoy).
SALE_BLOCKS = (
    "logo", "company", "branch", "header_text", "sale_info", "items", "totals",
    "payment", "loyalty", "messages", "footer_text", "barcode", "qr", "thanks",
)
#: Bloques del BOLETO de sorteo (diseño propio, no el de venta).
RAFFLE_BLOCKS = (
    "logo", "company", "branch", "raffle_title", "ticket_number", "customer", "prize",
    "draw_date", "sale_reference", "barcode", "qr", "legal_text", "footer_text",
)
BLOCK_LABELS = {
    "logo": "Logo", "company": "Nombre de la empresa", "branch": "Sucursal (nombre, "
    "dirección, teléfono)", "header_text": "Encabezado de la sucursal",
    "sale_info": "Folio, fecha, cajero y cliente", "items": "Productos",
    "totals": "Totales", "payment": "Forma de pago y cambio", "loyalty": "Puntos y nivel",
    "messages": "Mensajes y campañas", "footer_text": "Pie de la sucursal",
    "barcode": "Código de barras del folio", "qr": "Código QR", "thanks": "Agradecimiento",
    "raffle_title": "Nombre del sorteo", "ticket_number": "Número de boleto",
    "customer": "Cliente", "prize": "Premio", "draw_date": "Fecha del sorteo",
    "sale_reference": "Folio de la venta", "legal_text": "Texto legal / bases",
}
#: Bloques visibles por omisión (lo que el ticket imprimía antes).
_DEFAULT_OFF = {"logo", "barcode", "qr"}
_RAFFLE_DEFAULT_OFF = {"logo", "qr", "legal_text", "footer_text"}

#: Marcadores admitidos en la URL del QR — sólo datos públicos del ticket.
QR_PLACEHOLDERS = ("folio", "sucursal", "fecha", "total")
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")
MESSAGE_CATEGORIES = ("LOYALTY", "FOMO", "CTA")
DEFAULT_MESSAGE_MAX = {"LOYALTY": 1, "FOMO": 2, "CTA": 1}
MAX_TEXT = 300


@dataclass(frozen=True, slots=True)
class TicketBlock:
    type: str
    enabled: bool = True
    align: str = "center"
    #: Opciones propias del bloque (ancho del logo, URL del QR, textos...).
    options: dict = field(default_factory=dict)

    def option(self, key: str, default=None):
        return self.options.get(key, default)

    def to_dict(self) -> dict:
        data = {"type": self.type, "enabled": self.enabled, "align": self.align}
        if self.options:
            data["options"] = dict(self.options)
        return data


@dataclass(frozen=True, slots=True)
class TicketLayout:
    kind: str                       # "SALE" | "RAFFLE"
    blocks: tuple[TicketBlock, ...]
    paper: str = "AUTO"
    feed_lines: int = 4
    cut: bool = True

    # ── consulta ───────────────────────────────────────────────────────────
    def block(self, block_type: str) -> TicketBlock | None:
        return next((b for b in self.blocks if b.type == block_type), None)

    def enabled_blocks(self) -> tuple[TicketBlock, ...]:
        return tuple(b for b in self.blocks if b.enabled)

    def is_enabled(self, block_type: str) -> bool:
        found = self.block(block_type)
        return bool(found and found.enabled)

    def message_limits(self) -> dict[str, int]:
        """Máximo de mensajes por categoría; 0 = ninguno. Sin bloque de
        mensajes activo, ninguno."""
        found = self.block("messages")
        if found is None or not found.enabled:
            return {c: 0 for c in MESSAGE_CATEGORIES}
        limits = dict(DEFAULT_MESSAGE_MAX)
        limits.update({k: int(v) for k, v in (found.option("max") or {}).items()})
        return limits

    def qr_url(self) -> str:
        found = self.block("qr")
        return str(found.option("url", "") or "").strip() if found and found.enabled else ""

    # ── edición (inmutable) ────────────────────────────────────────────────
    def with_blocks(self, blocks: Iterable[TicketBlock]) -> "TicketLayout":
        return validate(replace(self, blocks=tuple(blocks)))

    # ── serialización ──────────────────────────────────────────────────────
    def to_json(self) -> str:
        return json.dumps({
            "schema": SCHEMA, "kind": self.kind, "paper": self.paper,
            "feed_lines": self.feed_lines, "cut": self.cut,
            "blocks": [b.to_dict() for b in self.blocks],
        }, ensure_ascii=False, indent=2)


def allowed_blocks(kind: str) -> tuple[str, ...]:
    return RAFFLE_BLOCKS if kind == "RAFFLE" else SALE_BLOCKS


def default_layout(kind: str = "SALE") -> TicketLayout:
    """El diseño por omisión: el mismo ticket que se imprimía hasta hoy (venta)
    o un boleto de sorteo con su número, premio y fecha."""
    if kind == "RAFFLE":
        off, names = _RAFFLE_DEFAULT_OFF, RAFFLE_BLOCKS
    else:
        off, names = _DEFAULT_OFF, SALE_BLOCKS
    blocks = []
    for name in names:
        align = "left" if name in ("sale_info", "items", "totals", "payment", "loyalty") else "center"
        options: dict[str, Any] = {}
        if name == "logo":
            options = {"width_pct": 60}
        elif name == "messages":
            options = {"max": dict(DEFAULT_MESSAGE_MAX)}
        elif name == "thanks":
            options = {"text": "Gracias por su compra"}
        elif name == "items":
            options = {"show_unit_price": True}
        elif name == "raffle_title":
            options = {"text": "BOLETO DE SORTEO"}
        blocks.append(TicketBlock(type=name, enabled=name not in off, align=align,
                                  options=options))
    return TicketLayout(kind=kind, blocks=tuple(blocks))


def is_layout_content(content: str) -> bool:
    try:
        data = json.loads(content or "")
    except (TypeError, ValueError):
        return False
    return isinstance(data, dict) and data.get("schema") == SCHEMA


def parse(content: str) -> TicketLayout:
    """El diseño guardado en una versión de plantilla. Lanza
    ``DocumentInvalidValueError`` con un motivo legible si no lo es."""
    try:
        data = json.loads(content or "")
    except (TypeError, ValueError) as exc:
        raise DocumentInvalidValueError(
            "El contenido no es un diseño de ticket: créalo con el diseñador de tickets "
            "(Configuración → Documentos → Diseñar).") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise DocumentInvalidValueError(
            "El contenido no es un diseño de ticket: créalo con el diseñador de tickets "
            "(Configuración → Documentos → Diseñar).")
    kind = str(data.get("kind") or "SALE").upper()
    if kind not in ("SALE", "RAFFLE"):
        raise DocumentInvalidValueError(f"Tipo de ticket desconocido: {kind}")
    blocks = []
    for raw in data.get("blocks") or ():
        if not isinstance(raw, dict):
            raise DocumentInvalidValueError("Bloque de ticket inválido")
        blocks.append(TicketBlock(
            type=str(raw.get("type") or ""), enabled=bool(raw.get("enabled", True)),
            align=str(raw.get("align") or "center"), options=dict(raw.get("options") or {})))
    try:
        feed = int(data.get("feed_lines", 4))
    except (TypeError, ValueError):
        feed = 4
    layout = TicketLayout(kind=kind, blocks=tuple(blocks),
                          paper=str(data.get("paper") or "AUTO"), feed_lines=feed,
                          cut=bool(data.get("cut", True)))
    return validate(layout)


def validate(layout: TicketLayout) -> TicketLayout:
    allowed = allowed_blocks(layout.kind)
    seen: set[str] = set()
    if not layout.blocks:
        raise DocumentInvalidValueError("El ticket necesita al menos un bloque")
    for block in layout.blocks:
        if block.type not in allowed:
            raise DocumentInvalidValueError(
                f"Bloque desconocido para este ticket: {block.type!r}")
        if block.type in seen:
            raise DocumentInvalidValueError(f"El bloque «{BLOCK_LABELS[block.type]}» se repite")
        seen.add(block.type)
        if block.align not in ALIGNMENTS:
            raise DocumentInvalidValueError(f"Alineación inválida: {block.align!r}")
        for key, value in block.options.items():
            if isinstance(value, str) and len(value) > MAX_TEXT:
                raise DocumentInvalidValueError(
                    f"«{BLOCK_LABELS[block.type]}»: el texto pasa de {MAX_TEXT} caracteres")
        if block.type == "logo":
            width = block.option("width_pct", 60)
            if not isinstance(width, (int, float)) or not 20 <= float(width) <= 100:
                raise DocumentInvalidValueError("El ancho del logo va de 20 % a 100 %")
        if block.type == "qr":
            url = str(block.option("url", "") or "").strip()
            if url:
                validate_qr_url(url)
            elif block.enabled:
                raise DocumentInvalidValueError(
                    "El QR activo necesita la dirección (URL) que va a abrir; sin URL, apágalo")
        if block.type == "messages":
            for category, value in (block.option("max") or {}).items():
                if category not in MESSAGE_CATEGORIES:
                    raise DocumentInvalidValueError(f"Categoría de mensaje desconocida: {category}")
                if not isinstance(value, int) or not 0 <= value <= 5:
                    raise DocumentInvalidValueError(
                        "El máximo de mensajes por categoría va de 0 a 5")
    if layout.paper not in PAPER_CHOICES:
        raise DocumentInvalidValueError(f"Ancho de papel inválido: {layout.paper!r}")
    if not 0 <= layout.feed_lines <= 10:
        raise DocumentInvalidValueError("Las líneas en blanco al final van de 0 a 10")
    return layout


def validate_qr_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://[^\s/$.?#][^\s]*$", url, re.I):
        raise DocumentInvalidValueError(
            "La URL del QR debe empezar con http:// o https:// y no llevar espacios")
    unknown = [p for p in _PLACEHOLDER.findall(url) if p not in QR_PLACEHOLDERS]
    if unknown:
        raise DocumentInvalidValueError(
            f"Marcadores no permitidos en la URL del QR: {', '.join(unknown)} "
            f"(se admiten: {', '.join('{' + p + '}' for p in QR_PLACEHOLDERS)})")
    return url


def fill_qr_url(url: str, values: dict[str, str]) -> str:
    """Sustituye los marcadores públicos, codificados para URL."""
    from urllib.parse import quote

    def sub(match):
        return quote(str(values.get(match.group(1), "") or ""), safe="")
    return _PLACEHOLDER.sub(sub, url)


def layout_for_document_type(document_type: str) -> str:
    return "RAFFLE" if document_type == "SWEEPSTAKES_TICKET" else "SALE"


#: Tipos de documento cuyo contenido es un diseño de ticket.
TICKET_DOCUMENT_TYPES = ("SALE_TICKET", "SWEEPSTAKES_TICKET")
