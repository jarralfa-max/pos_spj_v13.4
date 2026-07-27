from __future__ import annotations

from typing import Any, Dict, List

from core.ticket_escpos_renderer import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT_FULL,
    CUT_PARTIAL,
    DOUBLE_HW_ON,
    FEED_N,
    INIT,
    NORMAL,
    TicketESCPOSRenderer,
)
from core.tickets.ticket_layout_config import RAFFLE_BLOCK_ORDER, TicketLayoutConfig


class RaffleTicketESCPOSRenderer(TicketESCPOSRenderer):
    """ESC/POS renderer for loyalty raffle tickets.

    It only formats the printable payload; all eligibility and issuance rules
    belong to LoyaltyService/LoyaltyRepository.
    """

    def _raffle_layout_from_payload(self, ticket_data: Dict[str, Any]) -> TicketLayoutConfig:
        raw_config = dict(ticket_data.get("layout_config") or {})
        if not raw_config or "block_order" not in raw_config:
            merged = TicketLayoutConfig.for_layout_type("raffle_ticket").to_dict()
            merged.update(raw_config)
            if "blocks" in raw_config:
                merged["blocks"] = raw_config["blocks"]
            raw_config = merged
        return TicketLayoutConfig.from_dict(raw_config)

    def render(self, ticket_data: Dict[str, Any], logo_b64: str = "", qr_content: str = "") -> bytes:
        layout = self._raffle_layout_from_payload(ticket_data)
        width = int(getattr(layout, "chars_per_line", self.chars_per_line) or self.chars_per_line)
        qr_content = qr_content or str(ticket_data.get("qr_content") or ticket_data.get("numero_boleto") or "")
        buf = bytearray(INIT)
        for block_name in self._ordered_blocks(layout):
            if block_name not in RAFFLE_BLOCK_ORDER:
                continue
            if not self._block_enabled(layout, block_name):
                continue
            buf += self._render_raffle_block(block_name, ticket_data, layout, width, logo_b64, qr_content)
        feed_lines = max(0, min(10, int(getattr(layout, "feed_lines", 4) or 4)))
        buf += FEED_N + bytes([feed_lines])
        cut_type = str(getattr(layout, "cut_type", "partial") or "partial").lower()
        buf += CUT_PARTIAL if cut_type == "partial" else CUT_FULL
        return bytes(buf)

    def _render_raffle_block(self, block_name: str, data: Dict[str, Any], layout: TicketLayoutConfig, width: int, logo_b64: str, qr_content: str) -> bytes:
        if block_name == "logo":
            return self._logo_bytes(layout, logo_b64)
        if block_name == "brand_header":
            return self._brand_header_bytes(data, layout)
        if block_name == "raffle_title":
            title = data.get("raffle_name") or data.get("nombre") or "SORTEO"
            return self._separator(width) + ALIGN_CENTER + BOLD_ON + DOUBLE_HW_ON + self._text(title) + NORMAL + BOLD_OFF
        if block_name == "ticket_number":
            num = data.get("numero_boleto") or data.get("ticket_number") or ""
            return ALIGN_CENTER + BOLD_ON + self._text("BOLETO") + DOUBLE_HW_ON + self._text(num) + NORMAL + BOLD_OFF
        if block_name == "customer":
            if not getattr(layout, "show_customer", True):
                return b""
            cliente = data.get("cliente") or data.get("cliente_nombre") or "Público General"
            return ALIGN_LEFT + self._text(f"Cliente: {cliente}")
        if block_name == "sale_info":
            buf = bytearray(ALIGN_LEFT)
            if data.get("folio_venta"):
                buf += self._text(f"Venta: {data.get('folio_venta')}")
            if data.get("venta_id"):
                buf += self._text(f"ID venta: {data.get('venta_id')}")
            return bytes(buf)
        if block_name == "prize":
            premio = data.get("premio") or data.get("prize") or ""
            return (ALIGN_CENTER + self._text(f"Premio: {premio}")) if premio else b""
        if block_name == "draw_date":
            fecha = data.get("fecha_sorteo") or data.get("fecha_fin") or data.get("draw_date") or ""
            return (ALIGN_CENTER + self._text(f"Sorteo: {fecha}")) if fecha else b""
        if block_name == "qr":
            return self._qr_bytes(layout, qr_content)
        if block_name == "barcode":
            return self._barcode_bytes({"barcode": data.get("barcode") or data.get("numero_boleto")}, width)
        if block_name == "footer":
            msg = data.get("footer_message") or getattr(layout, "footer_message", "") or "Gracias por participar"
            return self._separator(width, char="-") + ALIGN_CENTER + self._text(msg)
        if block_name == "legal":
            msg = data.get("legal_message") or getattr(layout, "legal_message", "")
            return (ALIGN_CENTER + self._text(msg)) if msg else b""
        return b""

    def render_text_preview(self, ticket_data: Dict[str, Any], layout_config: TicketLayoutConfig | None = None) -> str:
        layout = layout_config or self._raffle_layout_from_payload(ticket_data)
        width = int(getattr(layout, "chars_per_line", self.chars_per_line) or self.chars_per_line)
        lines: List[str] = []
        lines.append(str(ticket_data.get("empresa", "SPJ POS")).center(width)[:width])
        lines.append("=" * width)
        lines.append(str(ticket_data.get("raffle_name", "SORTEO")).center(width)[:width])
        lines.append(f"BOLETO: {ticket_data.get('numero_boleto', '')}"[:width])
        if ticket_data.get("cliente"):
            lines.append(f"Cliente: {ticket_data.get('cliente')}"[:width])
        if ticket_data.get("folio_venta"):
            lines.append(f"Venta: {ticket_data.get('folio_venta')}"[:width])
        if ticket_data.get("premio"):
            lines.append(f"Premio: {ticket_data.get('premio')}"[:width])
        if ticket_data.get("fecha_sorteo") or ticket_data.get("fecha_fin"):
            lines.append(f"Sorteo: {ticket_data.get('fecha_sorteo') or ticket_data.get('fecha_fin')}"[:width])
        return "\n".join(lines)
