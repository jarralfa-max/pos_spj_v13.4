# core/ticket_escpos_renderer.py — SPJ POS
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import struct
from typing import Any, Dict, List, Optional

from core.tickets.ticket_layout_config import DEFAULT_BLOCK_ORDER, TicketLayoutConfig
from core.tickets.ticket_print_model import TicketPrintModel

logger = logging.getLogger("spj.escpos")

ESC = bytes([27])
GS = bytes([29])
INIT = ESC + b"@"
ALIGN_LEFT = ESC + b"a" + bytes([0])
ALIGN_CENTER = ESC + b"a" + bytes([1])
ALIGN_RIGHT = ESC + b"a" + bytes([2])
BOLD_ON = ESC + b"E" + bytes([1])
BOLD_OFF = ESC + b"E" + bytes([0])
DOUBLE_H_ON = ESC + b"!" + bytes([16])
DOUBLE_HW_ON = ESC + b"!" + bytes([48])
NORMAL = ESC + b"!" + bytes([0])
FEED_N = ESC + b"d"
CUT_FULL = GS + b"V" + bytes([0])
CUT_PARTIAL = GS + b"V" + bytes([66, 0])

CHARS_BY_WIDTH = {58: 32, 72: 42, 80: 48}
GENERIC_UNITS = {"", "pz", "pza", "pzas", "pieza", "piezas", "unidad", "unidades"}

_CODE39 = {
    "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn",
    "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw",
    "8": "wnnwnnwnn", "9": "nnwwnnwnn", "A": "wnnnnwnnw", "B": "nnwnnwnnw",
    "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn",
    "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
    "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww",
    "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn",
    "S": "nnwnnnwwn", "T": "nnnnwnwwn", "U": "wwnnnnnnw", "V": "nwwnnnnnw",
    "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "$": "nwnwnwnnn",
    "/": "nwnwnnnwn", "+": "nwnnnwnwn", "%": "nnnwnwnwn", "*": "nwnnwnwnn",
}


class TicketESCPOSRenderer:
    def __init__(self, paper_width_mm: int = 80, encoding: str = "cp850"):
        self.paper_width = int(paper_width_mm or 80)
        self.encoding = encoding or "cp850"
        self.chars_per_line = CHARS_BY_WIDTH.get(self.paper_width, 48)

    def render(self, ticket_data: Dict[str, Any] | TicketPrintModel,
               logo_b64: str = "", qr_content: str = "") -> bytes:
        if isinstance(ticket_data, TicketPrintModel):
            ticket_data = ticket_data.to_dict()
        layout = TicketLayoutConfig.from_dict(ticket_data.get("layout_config", {}))
        width = int(getattr(layout, "chars_per_line", self.chars_per_line) or self.chars_per_line)
        buf = bytearray(INIT)

        for block_name in self._ordered_blocks(layout):
            if not self._block_enabled(layout, block_name):
                continue
            buf += self._render_block(block_name, ticket_data, layout, width, logo_b64, qr_content)

        feed_lines = max(0, min(10, int(getattr(layout, "feed_lines", 4) or 4)))
        buf += FEED_N + bytes([feed_lines])
        cut_type = str(getattr(layout, "cut_type", "partial") or "partial").lower()
        buf += CUT_PARTIAL if cut_type == "partial" else CUT_FULL
        return bytes(buf)

    def _ordered_blocks(self, layout: TicketLayoutConfig) -> List[str]:
        configured = list(getattr(layout, "block_order", None) or DEFAULT_BLOCK_ORDER)
        blocks = getattr(layout, "blocks", {}) or {}
        extra = [b for b in blocks.keys() if b not in configured]
        ordered = configured + extra
        def _order(name: str) -> int:
            blk = blocks.get(name)
            return int(getattr(blk, "order", ordered.index(name)) if blk is not None else ordered.index(name))
        return sorted(ordered, key=_order)

    def _block_enabled(self, layout: TicketLayoutConfig, block_name: str) -> bool:
        flag_map = {
            "logo": "show_logo",
            "brand_header": "show_brand_name",
            "customer": "show_customer",
            "loyalty": "show_loyalty",
            "fomo": "show_fomo",
            "qr": "show_qr",
            "barcode": "show_barcode",
        }
        attr = flag_map.get(block_name)
        if attr and not bool(getattr(layout, attr, True)):
            return False
        blocks = getattr(layout, "blocks", {}) or {}
        blk = blocks.get(block_name)
        if blk is not None and hasattr(blk, "enabled"):
            return bool(blk.enabled)
        return True

    def _render_block(self, block_name: str, ticket_data: Dict[str, Any], layout: TicketLayoutConfig,
                      width: int, logo_b64: str, qr_content: str) -> bytes:
        if block_name == "logo":
            return self._logo_bytes(layout, logo_b64)
        if block_name == "brand_header":
            return self._brand_header_bytes(ticket_data, layout)
        if block_name == "sale_info":
            return self._sale_info_bytes(ticket_data, width)
        if block_name == "customer":
            return self._customer_bytes(ticket_data, layout)
        if block_name == "items":
            return self._items_bytes(ticket_data, width)
        if block_name == "totals":
            return self._totals_bytes(ticket_data, width)
        if block_name == "payment":
            return self._payment_bytes(ticket_data, width)
        if block_name == "loyalty":
            return self._loyalty_bytes(ticket_data, width)
        if block_name == "fomo":
            return self._fomo_bytes(ticket_data, width)
        if block_name == "qr":
            return self._qr_bytes(layout, qr_content)
        if block_name == "barcode":
            return self._barcode_bytes(ticket_data, width)
        if block_name == "footer":
            return self._footer_bytes(ticket_data, width)
        if block_name == "legal":
            return self._legal_bytes(ticket_data, width)
        return b""

    def render_safe_text(self, ticket_data: Dict[str, Any] | TicketPrintModel) -> bytes:
        text = self.render_text_preview(ticket_data)
        text += "\n\n\n"
        return text.encode(self.encoding, errors="replace")

    def _linebreak(self) -> bytes:
        return "\n".encode(self.encoding, errors="replace")

    def _align_cmd(self, alignment: str) -> bytes:
        value = str(alignment or "left").lower()
        if value == "center":
            return ALIGN_CENTER
        if value == "right":
            return ALIGN_RIGHT
        return ALIGN_LEFT

    def _logo_bytes(self, layout: TicketLayoutConfig, logo_b64: str) -> bytes:
        if not (getattr(layout, "show_logo", True) and logo_b64):
            return b""
        logo_bytes = self._render_logo(
            logo_b64,
            getattr(layout, "logo_size", "md"),
            debug_logo=getattr(layout, "ticket_debug_logo", False),
        )
        if not logo_bytes:
            return b""
        return self._align_cmd(getattr(layout, "logo_alignment", "center")) + logo_bytes + self._linebreak() + INIT

    def _brand_header_bytes(self, ticket_data: Dict[str, Any], layout: TicketLayoutConfig) -> bytes:
        buf = bytearray()
        empresa = ticket_data.get("empresa", "SPJ POS")
        slogan = ticket_data.get("slogan", ticket_data.get("brand_slogan", ""))
        empresa_dir = ticket_data.get("direccion", "")
        empresa_tel = ticket_data.get("telefono", "")
        rfc = ticket_data.get("rfc", ticket_data.get("empresa_rfc", ""))
        if getattr(layout, "show_brand_name", True):
            buf += ALIGN_CENTER + DOUBLE_HW_ON + self._text(empresa) + NORMAL
        if getattr(layout, "show_slogan", True) and slogan:
            buf += ALIGN_CENTER + self._text(slogan)
        if getattr(layout, "show_address", True) and empresa_dir:
            buf += ALIGN_CENTER + self._text(empresa_dir)
        if getattr(layout, "show_phone", True) and empresa_tel:
            buf += ALIGN_CENTER + self._text(f"Tel: {empresa_tel}")
        if getattr(layout, "show_rfc", False) and rfc:
            buf += ALIGN_CENTER + self._text(f"RFC: {rfc}")
        return bytes(buf)

    def _sale_info_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        buf = bytearray()
        buf += self._separator(width) + ALIGN_LEFT
        buf += BOLD_ON + self._text(f"Folio: {ticket_data.get('folio', '')}") + BOLD_OFF
        if ticket_data.get("fecha"):
            buf += self._text(f"Fecha: {ticket_data.get('fecha', '')}")
        if ticket_data.get("cajero"):
            buf += self._text(f"Cajero: {ticket_data.get('cajero', '')}")
        return bytes(buf)

    def _customer_bytes(self, ticket_data: Dict[str, Any], layout: TicketLayoutConfig) -> bytes:
        if not getattr(layout, "show_customer", True):
            return b""
        cliente = ticket_data.get("cliente") or ticket_data.get("cliente_nombre") or "Público General"
        return ALIGN_LEFT + self._text(f"Cliente: {cliente}")

    def _item_name(self, item: Dict[str, Any]) -> str:
        return str(
            item.get("nombre")
            or item.get("name")
            or item.get("producto")
            or item.get("product_name")
            or item.get("descripcion")
            or f"Producto {item.get('product_id', '')}"
        )

    def _item_unit(self, item: Dict[str, Any]) -> str:
        db_unit = str(item.get("db_unidad") or item.get("unidad_db") or item.get("unidad_producto") or "").strip()
        payload_unit = str(item.get("unidad") or item.get("unit") or item.get("unidad_medida") or item.get("unit_name") or item.get("uom") or "").strip()
        if db_unit and payload_unit.lower() in GENERIC_UNITS:
            return db_unit
        return db_unit or payload_unit or "pz"

    def _items_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        buf = bytearray()
        buf += self._separator(width)
        buf += BOLD_ON + self._columns("PRODUCTO", "CANT", "TOTAL", width) + BOLD_OFF
        buf += self._separator(width, char="-")
        for item in ticket_data.get("items", []):
            nombre = self._item_name(item)
            cant = float(item.get("cantidad", item.get("qty", item.get("quantity", 0))) or 0)
            unidad = self._item_unit(item)
            precio = float(item.get("precio_unitario", item.get("unit_price", 0)) or 0)
            total_it = float(item.get("total", item.get("subtotal", cant * precio)) or 0)
            cant_str = f"{cant:.2f}{unidad}"
            total_str = f"${total_it:.2f}"
            col_nombre = max(8, width - 18)
            if len(nombre) > col_nombre:
                buf += self._text(nombre)
                buf += self._columns("", cant_str, total_str, width)
            else:
                buf += self._columns(nombre, cant_str, total_str, width)
        return bytes(buf)

    def _totals_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        buf = bytearray()
        buf += self._separator(width)
        totales = ticket_data.get("totales", {}) or {}
        subtotal = float(totales.get("subtotal", ticket_data.get("subtotal", 0)) or 0)
        descuento = float(totales.get("descuento", ticket_data.get("descuento", 0)) or 0)
        total_final = float(totales.get("total_final", ticket_data.get("total_final", ticket_data.get("total", subtotal))) or 0)
        buf += ALIGN_RIGHT
        if descuento > 0:
            buf += self._text(f"Subtotal: ${subtotal:.2f}")
            buf += self._text(f"Descuento: -${descuento:.2f}")
        buf += BOLD_ON + DOUBLE_H_ON + self._text(f"TOTAL: ${total_final:.2f}") + NORMAL + BOLD_OFF
        return bytes(buf)

    def _payment_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        pago = ticket_data.get("pago", {}) or {}
        if not pago.get("forma_pago"):
            return b""
        total_final = float((ticket_data.get("totales", {}) or {}).get("total_final", ticket_data.get("total", 0)) or 0)
        buf = bytearray()
        buf += ALIGN_LEFT + self._separator(width, char="-")
        buf += self._text(f"Forma de pago: {pago.get('forma_pago', '')}")
        if str(pago.get("forma_pago", "")).lower() == "efectivo":
            buf += self._text(f"Recibido: ${float(pago.get('efectivo_recibido', total_final) or 0):.2f}")
            buf += self._text(f"Cambio: ${float(pago.get('cambio', 0) or 0):.2f}")
        return bytes(buf)

    def _loyalty_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        loyalty = dict(ticket_data.get("loyalty") or {})
        pts = loyalty.get("puntos_ganados", ticket_data.get("puntos_ganados"))
        total_pts = loyalty.get("puntos_totales", ticket_data.get("puntos_totales"))
        nivel = loyalty.get("nivel", ticket_data.get("nivel_cliente", ""))
        mensaje = loyalty.get("mensaje", "")
        available = bool(loyalty.get("available", ticket_data.get("puntos_disponibles", False)))
        if pts in (None, "") and total_pts in (None, "") and not mensaje and not nivel:
            return b""
        buf = bytearray()
        buf += self._separator(width, char="-") + ALIGN_CENTER
        if pts not in (None, "", 0):
            buf += self._text(f"Puntos ganados: +{pts}")
        if available and total_pts not in (None, ""):
            buf += self._text(f"Saldo puntos: {total_pts}")
        if nivel:
            buf += self._text(f"Nivel: {nivel}")
        if mensaje:
            buf += self._text(mensaje)
        return bytes(buf)

    def _fomo_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        raw = ticket_data.get("fomo_messages") or ticket_data.get("fomo") or ticket_data.get("mensajes_fomo") or []
        if isinstance(raw, str):
            raw = [{"message": raw}]
        if not raw:
            msg = ticket_data.get("mensaje_fomo") or ""
            raw = [{"message": msg}] if msg else []
        messages = []
        for item in raw:
            if isinstance(item, dict):
                msg = item.get("message") or item.get("mensaje") or item.get("text") or ""
            else:
                msg = str(item or "")
            if msg:
                messages.append(str(msg))
        if not messages:
            return b""
        buf = bytearray()
        buf += self._separator(width, char="-") + ALIGN_CENTER
        for msg in messages[:3]:
            buf += self._text(msg)
        return bytes(buf)

    def _qr_bytes(self, layout: TicketLayoutConfig, qr_content: str) -> bytes:
        if not (getattr(layout, "show_qr", True) and qr_content):
            return b""
        qr_bytes = self._render_qr(qr_content)
        if not qr_bytes:
            return b""
        return ALIGN_CENTER + qr_bytes + self._linebreak() + INIT

    def _barcode_value(self, ticket_data: Dict[str, Any]) -> str:
        for key in ("barcode", "codigo_barras", "codigo", "folio"):
            value = str(ticket_data.get(key) or "").strip()
            if value:
                return value
        return ""

    def _barcode_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        value = self._barcode_value(ticket_data)
        if not value:
            return b""
        img_bytes = self._render_code39_as_image(value)
        if not img_bytes:
            return b""
        return self._separator(width, char="-") + ALIGN_CENTER + img_bytes + self._linebreak() + INIT

    def _footer_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        msg = ticket_data.get("mensaje_psicologico", ticket_data.get("footer_message", "¡Gracias por su compra!"))
        if not msg:
            return b""
        return self._separator(width) + ALIGN_CENTER + self._text(msg) + self._text("")

    def _legal_bytes(self, ticket_data: Dict[str, Any], width: int) -> bytes:
        msg = ticket_data.get("legal_message") or ticket_data.get("mensaje_legal") or ""
        if not msg:
            return b""
        return self._separator(width, char="-") + ALIGN_CENTER + self._text(msg)

    def _text(self, text: Any) -> bytes:
        return (self._sanitize_text(text) + "\n").encode(self.encoding, errors="replace")

    def _separator(self, width: int, char: str = "=") -> bytes:
        return (char * int(width or self.chars_per_line) + "\n").encode(self.encoding, errors="replace")

    def _columns(self, left: str, middle: str, right: str, width: int) -> bytes:
        mid_w = max(8, len(str(middle)) + 1)
        right_w = max(9, len(str(right)) + 1)
        left_w = max(1, width - mid_w - right_w)
        line = f"{self._sanitize_text(left)[:left_w].ljust(left_w)}{self._sanitize_text(middle)[:mid_w].rjust(mid_w)}{self._sanitize_text(right)[:right_w].rjust(right_w)}\n"
        return line.encode(self.encoding, errors="replace")

    def _sanitize_text(self, text: Any) -> str:
        raw = str(text or "")
        raw = re.sub(r"[\U00010000-\U0010ffff]", "", raw)
        raw = "".join(ch for ch in raw if ch in "\n\t" or ord(ch) >= 32)
        return raw

    def render_text_preview(self, ticket_data: Dict[str, Any] | TicketPrintModel,
                            layout_config: Optional[TicketLayoutConfig] = None) -> str:
        if isinstance(ticket_data, TicketPrintModel):
            ticket_data = ticket_data.to_dict()
        layout = layout_config or TicketLayoutConfig.from_dict(ticket_data.get("layout_config", {}))
        width = int(getattr(layout, "chars_per_line", self.chars_per_line) or self.chars_per_line)
        lines: List[str] = []
        lines.append(self._sanitize_text(ticket_data.get("empresa", "SPJ POS")).center(width)[:width])
        if ticket_data.get("direccion"):
            lines.append(self._sanitize_text(ticket_data.get("direccion", ""))[:width])
        lines.append("=" * width)
        lines.append(f"Folio: {self._sanitize_text(ticket_data.get('folio', ''))}"[:width])
        if ticket_data.get("fecha"):
            lines.append(f"Fecha: {self._sanitize_text(ticket_data.get('fecha', ''))}"[:width])
        if ticket_data.get("cajero"):
            lines.append(f"Cajero: {self._sanitize_text(ticket_data.get('cajero', ''))}"[:width])
        if getattr(layout, "show_customer", True):
            lines.append(f"Cliente: {self._sanitize_text(ticket_data.get('cliente', ticket_data.get('cliente_nombre', 'Público General')))}"[:width])
        lines.append("-" * width)
        for item in ticket_data.get("items", []):
            nombre = self._item_name(item)
            qty = float(item.get("cantidad", item.get("qty", item.get("quantity", 0))) or 0)
            unidad = self._item_unit(item)
            total_it = float(item.get("total", item.get("subtotal", 0)) or 0)
            left_w = max(10, width - 14)
            for i in range(0, len(nombre), left_w):
                chunk = nombre[i:i + left_w]
                if i == 0:
                    lines.append(f"{chunk:<{left_w}} {qty:>5.2f}{unidad} ${total_it:>6.2f}"[:width])
                else:
                    lines.append(chunk[:width])
        total = float((ticket_data.get("totales", {}) or {}).get("total_final", ticket_data.get("total_final", ticket_data.get("total", 0))) or 0)
        lines.append("=" * width)
        lines.append(f"TOTAL: ${total:.2f}".rjust(width)[:width])
        pago = ticket_data.get("pago", {}) or {}
        if pago.get("forma_pago"):
            lines.append(f"Pago: {self._sanitize_text(pago.get('forma_pago'))}"[:width])
            if str(pago.get("forma_pago", "")).lower() == "efectivo":
                recibido = float(pago.get("efectivo_recibido", pago.get("amount_paid_real", 0)) or 0)
                cambio = float(pago.get("cambio", 0) or 0)
                lines.append(f"Recibido: ${recibido:.2f}"[:width])
                lines.append(f"Cambio: ${cambio:.2f}"[:width])
        lines.append("-" * width)
        lines.append(self._sanitize_text(ticket_data.get("mensaje_psicologico", "¡Gracias por su compra!")).center(width)[:width])
        return "\n".join(lines)

    def _logo_debug_enabled(self, debug_logo: Any = None) -> bool:
        explicit = str(debug_logo).strip().lower() in {"1", "true", "si", "sí", "yes", "on"}
        env_enabled = str(os.environ.get("ticket_debug_logo", os.environ.get("TICKET_DEBUG_LOGO", ""))).strip() == "1"
        return explicit or env_enabled

    def _logo_target_size(self, logo_size: str) -> tuple[int, int]:
        size_key = str(logo_size or "md").lower()
        try:
            numeric_width = int(float(size_key))
        except Exception:
            numeric_width = None
        if numeric_width:
            return max(80, min(384 if self.paper_width <= 58 else 512, numeric_width)), 180 if self.paper_width <= 58 else 240
        size_map_58 = {"sm": (192, 80), "md": (320, 140), "lg": (384, 180), "xl": (384, 220)}
        size_map_80 = {"sm": (240, 100), "md": (384, 160), "lg": (512, 240), "xl": (512, 280)}
        return (size_map_58 if self.paper_width <= 58 else size_map_80).get(
            size_key,
            (320, 140) if self.paper_width <= 58 else (384, 160),
        )

    def _decode_logo_b64(self, logo_b64: str) -> bytes:
        raw_logo_b64 = str(logo_b64 or "").strip()
        if "," in raw_logo_b64:
            raw_logo_b64 = raw_logo_b64.split(",", 1)[1]
        raw_logo_b64 = "".join(raw_logo_b64.split())
        return base64.b64decode(raw_logo_b64, validate=False)

    def _compose_logo_on_white(self, input_img):
        from PIL import Image

        original_mode = input_img.mode
        has_alpha = original_mode in ("RGBA", "LA") or (original_mode == "P" and "transparency" in input_img.info)
        if not has_alpha:
            # Sin canal alfa: si el logo tiene un fondo sólido de color (no blanco),
            # el umbral térmico lo imprimiría como bloque negro. Se detecta el color
            # de fondo por las esquinas y se pinta de blanco (no imprime).
            return self._drop_solid_background(input_img.convert("RGB")), None

        rgba = input_img.convert("RGBA")
        alpha = rgba.getchannel("A")
        white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        composed = Image.alpha_composite(white, rgba).convert("L")
        # Fully/mostly transparent pixels must be pure white before thresholding; otherwise
        # transparent PNG backgrounds become dark thermal speckles on some printers.
        transparent_mask = alpha.point(lambda a: 255 if a <= 32 else 0)
        composed.paste(255, mask=transparent_mask)
        return composed, alpha

    def _drop_solid_background(self, rgb):
        """Convierte a escala de grises quitando un fondo sólido de color.

        Si las 4 esquinas comparten un color (fondo sólido) y ese color no es ya
        casi-blanco, los píxeles de ese color se pintan de blanco (255) para que la
        impresora térmica no los imprima como bloque. No toca logos con fondo blanco
        (el umbral ya los descarta) ni con transparencia (esa ruta va aparte)."""
        w, h = rgb.size
        l = rgb.convert("L")
        if w == 0 or h == 0:
            return l
        corners = [rgb.getpixel((0, 0)), rgb.getpixel((w - 1, 0)),
                   rgb.getpixel((0, h - 1)), rgb.getpixel((w - 1, h - 1))]
        br, bg, bb = corners[0]
        uniforme = all(abs(c[0] - br) <= 24 and abs(c[1] - bg) <= 24 and abs(c[2] - bb) <= 24
                       for c in corners)
        if uniforme and not (br >= 230 and bg >= 230 and bb >= 230):
            tol = 45
            _rgb_px = getattr(rgb, "get_flattened_data", rgb.getdata)()
            _l_px = getattr(l, "get_flattened_data", l.getdata)()
            nuevos = [
                255 if (abs(r - br) <= tol and abs(g - bg) <= tol and abs(b - bb) <= tol) else lum
                for (r, g, b), lum in zip(_rgb_px, _l_px)
            ]
            l.putdata(nuevos)
        return l

    def _resize_and_pad_logo(self, img, logo_size: str):
        from PIL import Image

        max_dots_w, max_dots_h = self._logo_target_size(logo_size)
        ratio = min(max_dots_w / max(1, img.width), max_dots_h / max(1, img.height), 1.0)
        if ratio < 1.0:
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.BICUBIC)
            img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))), resampling)
        if img.width % 8 != 0:
            new_w = img.width + (8 - img.width % 8)
            new_img = Image.new("L", (new_w, img.height), 255)
            new_img.paste(img, (0, 0))
            img = new_img
        return img

    def _dump_logo_diagnostics(self, input_img, processed, *, logo_size: str, original_mode: str, had_alpha: bool, threshold: int) -> None:
        os.makedirs("logs", exist_ok=True)
        try:
            input_img.save("logs/ticket_logo_input.png")
            processed.convert("L").save("logs/ticket_logo_processed.png")
            with open("logs/ticket_logo_info.json", "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "mode": original_mode,
                        "size": list(input_img.size),
                        "processed_size": list(processed.size),
                        "logo_size": logo_size,
                        "had_alpha": had_alpha,
                        "threshold": threshold,
                    },
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as diag_exc:
            logger.debug("No se pudo guardar diagnóstico de logo: %s", diag_exc)

    def _render_logo(self, logo_b64: str, logo_size: str = "md", debug_logo: Any = None) -> Optional[bytes]:
        try:
            from PIL import Image
            img_bytes = self._decode_logo_b64(logo_b64)
            input_img = Image.open(io.BytesIO(img_bytes))
            input_img.load()
            original_mode = input_img.mode
            img, alpha = self._compose_logo_on_white(input_img)
            img = self._resize_and_pad_logo(img, logo_size)
            threshold = 150
            processed = img.point(lambda x: 0 if x < threshold else 255, "1")
            if self._logo_debug_enabled(debug_logo):
                self._dump_logo_diagnostics(
                    input_img,
                    processed,
                    logo_size=logo_size,
                    original_mode=original_mode,
                    had_alpha=alpha is not None,
                    threshold=threshold,
                )
            return self._image_to_escpos_raster(processed)
        except ImportError:
            logger.warning("Pillow no instalado — logo no se imprimirá. Instalar: pip install Pillow")
            return None
        except Exception as exc:
            logger.warning("Error renderizando logo: %s", exc)
            return None

    def _render_code39_as_image(self, value: str) -> Optional[bytes]:
        try:
            from PIL import Image, ImageDraw
            clean = re.sub(r"[^A-Za-z0-9\-\. \$/\+%]", "", str(value or "")).upper()[:32]
            if not clean:
                clean = "SPJ"
            data = f"*{clean}*"
            narrow = 2
            wide = 5
            height = 72 if self.paper_width <= 58 else 90
            quiet = 18
            total_w = quiet * 2
            for ch in data:
                pattern = _CODE39.get(ch, _CODE39["-"])
                total_w += sum(wide if p == "w" else narrow for p in pattern) + narrow
            max_w = 360 if self.paper_width <= 58 else 512
            scale = min(1.0, max_w / max(1, total_w))
            narrow = max(1, int(narrow * scale))
            wide = max(3, int(wide * scale))
            quiet = max(10, int(quiet * scale))
            total_w = quiet * 2
            for ch in data:
                pattern = _CODE39.get(ch, _CODE39["-"])
                total_w += sum(wide if p == "w" else narrow for p in pattern) + narrow
            img = Image.new("L", (total_w + (8 - total_w % 8 if total_w % 8 else 0), height + 18), 255)
            draw = ImageDraw.Draw(img)
            x = quiet
            for ch in data:
                pattern = _CODE39.get(ch, _CODE39["-"])
                for idx, p in enumerate(pattern):
                    bar_w = wide if p == "w" else narrow
                    if idx % 2 == 0:
                        draw.rectangle([x, 0, x + bar_w - 1, height], fill=0)
                    x += bar_w
                x += narrow
            img = img.point(lambda px: 0 if px < 128 else 255, "1")
            return self._image_to_escpos_raster(img)
        except Exception as exc:
            logger.warning("Error renderizando código de barras: %s", exc)
            return None

    def _image_to_escpos_raster(self, img) -> bytes:
        width_bytes = img.width // 8
        height = img.height
        pixels = img.tobytes()
        buf = bytearray()
        buf += GS + b"v0" + bytes([0])
        buf += struct.pack("<H", width_bytes)
        buf += struct.pack("<H", height)
        buf += pixels
        return bytes(buf)

    def _render_qr(self, content: str) -> Optional[bytes]:
        try:
            import qrcode
            from PIL import Image
            qr = qrcode.QRCode(version=1, box_size=4, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("L")
            max_w = 224 if self.paper_width <= 58 else 320
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((int(img.width * ratio), int(img.height * ratio)))
            if img.width % 8 != 0:
                new_w = img.width + (8 - img.width % 8)
                new_img = Image.new("L", (new_w, img.height), 255)
                new_img.paste(img, (0, 0))
                img = new_img
            img = img.point(lambda x: 0 if x < 128 else 255, "1")
            return self._image_to_escpos_raster(img)
        except Exception as exc:
            logger.debug("QR render error: %s", exc)
            return None

    def send(self, data: bytes, tipo: str = "", ubicacion: str = "", cfg: Dict = None) -> bool:
        from core.services.printer_service import PrintTransport, TransportType
        if cfg:
            tipo = str(cfg.get("tipo", tipo)).lower()
            ubicacion = str(cfg.get("ubicacion", ubicacion))
            try:
                tipo_idx = int(cfg.get("tipo_idx", -1))
                if tipo_idx == 0:
                    tipo = "usb_win32"
                elif tipo_idx == 2:
                    tipo = "network"
            except Exception:
                pass
        transport = TransportType.AUTO
        if "win32" in tipo or "usb" in tipo:
            transport = TransportType.USB_WIN32
        elif "red" in tipo or "tcp" in tipo or ":" in ubicacion:
            transport = TransportType.NETWORK
        elif "serial" in tipo or "com" in tipo.lower():
            transport = TransportType.SERIAL
        return PrintTransport.send(data, transport, ubicacion)


def render_and_print_ticket(ticket_data: Dict[str, Any], printer_cfg: Dict = None, db_conn=None) -> bool:
    if not printer_cfg:
        return False
    paper_w = 80
    try:
        paper_w = int(printer_cfg.get("paper_width", 80) or 80)
    except Exception:
        pass
    renderer = TicketESCPOSRenderer(paper_width_mm=paper_w)
    data = renderer.render(ticket_data)
    return renderer.send(data, cfg=printer_cfg)
