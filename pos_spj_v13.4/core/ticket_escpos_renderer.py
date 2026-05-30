# core/ticket_escpos_renderer.py — SPJ POS
"""ESC/POS ticket renderer.

Two output modes are intentionally supported:

1. ``render``: raw ESC/POS with binary control commands, images and optional cut.
   Use this only with printers/transports that accept ESC/POS RAW.
2. ``render_safe_text``: plain monospaced bytes with no ESC/POS binary commands.
   Use this with Windows drivers that print raw command bytes as symbols.

If a ticket prints long garbage/symbols, the wrong mode/driver is being used.
Do not hide that by adding fallbacks that still send image/QR bytes.
"""
from __future__ import annotations

import io
import logging
import re
import struct
from typing import Any, Dict, List, Optional

from core.tickets.ticket_print_model import TicketPrintModel
from core.tickets.ticket_layout_config import TicketLayoutConfig

logger = logging.getLogger("spj.escpos")

ESC = b"\x1b"
GS = b"\x1d"
INIT = ESC + b"@"
ALIGN_LEFT = ESC + b"a\x00"
ALIGN_CENTER = ESC + b"a\x01"
ALIGN_RIGHT = ESC + b"a\x02"
BOLD_ON = ESC + b"E\x01"
BOLD_OFF = ESC + b"E\x00"
DOUBLE_H_ON = ESC + b"!\x10"
DOUBLE_HW_ON = ESC + b"!\x30"
NORMAL = ESC + b"!\x00"
FEED_N = ESC + b"d"
CUT_FULL = GS + b"V\x00"
CUT_PARTIAL = GS + b"V\x42\x00"

CHARS_BY_WIDTH = {58: 32, 72: 42, 80: 48}


class TicketESCPOSRenderer:
    def __init__(self, paper_width_mm: int = 80, encoding: str = "cp850"):
        self.paper_width = int(paper_width_mm or 80)
        self.encoding = encoding or "cp850"
        self.chars_per_line = CHARS_BY_WIDTH.get(self.paper_width, 48)

    def render(self, ticket_data: Dict[str, Any] | TicketPrintModel,
               logo_b64: str = "", qr_content: str = "") -> bytes:
        """Render full raw ESC/POS bytes.

        This mode may include binary image/QR/cut commands. It must only be sent
        to a real ESC/POS RAW transport. If a driver prints symbols, use
        ``render_safe_text`` instead.
        """
        if isinstance(ticket_data, TicketPrintModel):
            ticket_data = ticket_data.to_dict()
        layout = TicketLayoutConfig.from_dict(ticket_data.get("layout_config", {}))
        w = layout.chars_per_line
        buf = bytearray()
        buf += INIT

        if layout.show_logo and logo_b64:
            logo_bytes = self._render_logo(logo_b64)
            if logo_bytes:
                buf += ALIGN_CENTER + logo_bytes + b"\n"

        empresa = ticket_data.get("empresa", "SPJ POS")
        empresa_dir = ticket_data.get("direccion", "")
        empresa_tel = ticket_data.get("telefono", "")
        buf += ALIGN_CENTER + DOUBLE_HW_ON + self._text(empresa) + NORMAL
        if empresa_dir:
            buf += self._text(empresa_dir)
        if empresa_tel:
            buf += self._text(f"Tel: {empresa_tel}")

        buf += self._separator(w) + ALIGN_LEFT
        buf += BOLD_ON + self._text(f"Folio: {ticket_data.get('folio', '')}") + BOLD_OFF
        buf += self._text(f"Fecha: {ticket_data.get('fecha', '')}")
        buf += self._text(f"Cajero: {ticket_data.get('cajero', '')}")
        buf += self._text(f"Cliente: {ticket_data.get('cliente', 'Público General')}")

        buf += self._items_and_totals_bytes(ticket_data, w)

        if layout.show_qr and qr_content:
            qr_bytes = self._render_qr(qr_content)
            if qr_bytes:
                buf += ALIGN_CENTER + qr_bytes

        buf += self._footer_bytes(ticket_data, w)
        buf += FEED_N + bytes([max(0, min(10, int(layout.feed_lines)))])
        buf += CUT_PARTIAL if layout.cut_type == "partial" else CUT_FULL
        return bytes(buf)

    def render_safe_text(self, ticket_data: Dict[str, Any] | TicketPrintModel) -> bytes:
        """Render plain text only. No ESC/POS binary commands, image, QR or cut."""
        text = self.render_text_preview(ticket_data)
        text += "\n\n\n"
        return text.encode(self.encoding, errors="replace")

    def _items_and_totals_bytes(self, ticket_data: Dict[str, Any], w: int) -> bytes:
        buf = bytearray()
        buf += self._separator(w)
        buf += BOLD_ON + self._columns("PRODUCTO", "CANT", "TOTAL", w) + BOLD_OFF
        buf += self._separator(w, char="-")
        for item in ticket_data.get("items", []):
            nombre = str(item.get("nombre", ""))
            cant = float(item.get("cantidad", item.get("qty", 0)) or 0)
            unidad = str(item.get("unidad", "pz"))
            precio = float(item.get("precio_unitario", item.get("unit_price", 0)) or 0)
            total_it = float(item.get("total", item.get("subtotal", cant * precio)) or 0)
            cant_str = f"{cant:.2f}{unidad}"
            total_str = f"${total_it:.2f}"
            col_nombre = w - 18
            if len(nombre) > col_nombre:
                buf += self._text(nombre)
                buf += self._columns("", cant_str, total_str, w)
            else:
                buf += self._columns(nombre, cant_str, total_str, w)
        buf += self._separator(w)
        totales = ticket_data.get("totales", {}) or {}
        subtotal = float(totales.get("subtotal", 0) or 0)
        descuento = float(totales.get("descuento", 0) or 0)
        total_final = float(totales.get("total_final", subtotal) or 0)
        buf += ALIGN_RIGHT
        if descuento > 0:
            buf += self._text(f"Subtotal: ${subtotal:.2f}")
            buf += self._text(f"Descuento: -${descuento:.2f}")
        buf += BOLD_ON + DOUBLE_H_ON + self._text(f"TOTAL: ${total_final:.2f}") + NORMAL + BOLD_OFF
        pago = ticket_data.get("pago", {}) or {}
        if pago.get("forma_pago"):
            buf += ALIGN_LEFT + self._separator(w, char="-")
            buf += self._text(f"Forma de pago: {pago.get('forma_pago', '')}")
            if str(pago.get("forma_pago", "")).lower() == "efectivo":
                buf += self._text(f"Recibido: ${float(pago.get('efectivo_recibido', total_final) or 0):.2f}")
                buf += self._text(f"Cambio: ${float(pago.get('cambio', 0) or 0):.2f}")
        loyalty = dict(ticket_data.get("loyalty") or {})
        pts = loyalty.get("puntos_ganados", ticket_data.get("puntos_ganados"))
        if pts not in (None, "", 0):
            buf += self._separator(w, char="-") + ALIGN_CENTER
            buf += self._text(f"Puntos ganados: +{pts}")
            total_pts = loyalty.get("puntos_totales", ticket_data.get("puntos_totales"))
            if loyalty.get("available", False) and total_pts not in (None, ""):
                buf += self._text(f"Saldo total: {total_pts} puntos")
        return bytes(buf)

    def _footer_bytes(self, ticket_data: Dict[str, Any], w: int) -> bytes:
        return self._separator(w) + ALIGN_CENTER + self._text(ticket_data.get("mensaje_psicologico", "¡Gracias por su compra!")) + self._text("")

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
        w = layout.chars_per_line
        lines: List[str] = []
        lines.append(self._sanitize_text(ticket_data.get("empresa", "SPJ POS")).center(w)[:w])
        if ticket_data.get("direccion"):
            lines.append(self._sanitize_text(ticket_data.get("direccion", ""))[:w])
        lines.append("=" * w)
        lines.append(f"Folio: {self._sanitize_text(ticket_data.get('folio', ''))}"[:w])
        if ticket_data.get("fecha"):
            lines.append(f"Fecha: {self._sanitize_text(ticket_data.get('fecha', ''))}"[:w])
        if ticket_data.get("cajero"):
            lines.append(f"Cajero: {self._sanitize_text(ticket_data.get('cajero', ''))}"[:w])
        lines.append("-" * w)
        for item in ticket_data.get("items", []):
            nombre = self._sanitize_text(item.get("nombre", ""))
            qty = float(item.get("cantidad", item.get("qty", 0)) or 0)
            total_it = float(item.get("total", item.get("subtotal", 0)) or 0)
            left_w = max(10, w - 14)
            for i in range(0, len(nombre), left_w):
                chunk = nombre[i:i + left_w]
                if i == 0:
                    lines.append(f"{chunk:<{left_w}} {qty:>5.2f} ${total_it:>6.2f}"[:w])
                else:
                    lines.append(chunk[:w])
        total = float((ticket_data.get("totales", {}) or {}).get("total_final", 0) or 0)
        lines.append("=" * w)
        lines.append(f"TOTAL: ${total:.2f}".rjust(w)[:w])
        pago = ticket_data.get("pago", {}) or {}
        if pago.get("forma_pago"):
            lines.append(f"Pago: {self._sanitize_text(pago.get('forma_pago'))}"[:w])
        lines.append("-" * w)
        lines.append(self._sanitize_text(ticket_data.get("mensaje_psicologico", "¡Gracias por su compra!")).center(w)[:w])
        return "\n".join(lines)

    def _render_logo(self, logo_b64: str) -> Optional[bytes]:
        try:
            from PIL import Image
            import base64
            if "," in logo_b64:
                logo_b64 = logo_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(logo_b64)
            img = Image.open(io.BytesIO(img_bytes)).convert("L")
            max_dots_w = min((self.paper_width - 10) * 8, 384)
            if img.width > max_dots_w:
                ratio = max_dots_w / img.width
                img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
            if img.width % 8 != 0:
                new_w = img.width + (8 - img.width % 8)
                new_img = Image.new("L", (new_w, img.height), 255)
                new_img.paste(img, (0, 0))
                img = new_img
            img = img.point(lambda x: 0 if x < 128 else 255, "1")
            return self._image_to_escpos_raster(img)
        except ImportError:
            logger.warning("Pillow no instalado — logo no se imprimirá. Instalar: pip install Pillow")
            return None
        except Exception as exc:
            logger.warning("Error renderizando logo: %s", exc)
            return None

    def _image_to_escpos_raster(self, img) -> bytes:
        width_bytes = img.width // 8
        height = img.height
        pixels = img.tobytes()
        buf = bytearray()
        buf += GS + b"v0" + b"\x00"
        buf += struct.pack("<H", width_bytes)
        buf += struct.pack("<H", height)
        buf += pixels
        return bytes(buf)

    def _render_qr(self, content: str) -> Optional[bytes]:
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=4, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white").convert("L")
            max_w = min((self.paper_width - 20) * 8, 320)
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize((int(img.width * ratio), int(img.height * ratio)))
            if img.width % 8 != 0:
                new_w = img.width + (8 - img.width % 8)
                new_img = __import__("PIL.Image", fromlist=["Image"]).new("L", (new_w, img.height), 255)
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
