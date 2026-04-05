# core/ticket_escpos_renderer.py — SPJ POS v13.30
"""
Renderer ESC/POS para impresoras térmicas.

Genera bytes raw ESC/POS con soporte para:
- Logo (base64 → bitmap ESC/POS)
- Texto centrado, izquierda, derecha
- Negrita, doble altura/ancho
- Tablas con columnas alineadas
- QR codes como bitmap
- Corte de papel

POR QUÉ HTML NO FUNCIONA EN IMPRESORAS TÉRMICAS:
Las impresoras térmicas no tienen motor HTML/CSS. Reciben bytes raw
con comandos ESC/POS (Epson Standard Code for Point of Sale).
Cuando QPrinter "imprime" HTML, lo rasteriza como si fuera una
impresora láser a 300dpi — pero las térmicas operan a 8 dots/mm
(203 dpi) con ancho fijo de 48-80mm. El resultado es texto cortado,
imágenes ausentes y alineación rota.

USO:
    from core.ticket_escpos_renderer import TicketESCPOSRenderer

    renderer = TicketESCPOSRenderer(paper_width_mm=80)
    data = renderer.render(ticket_data)  # bytes listos para enviar
    renderer.send(data, tipo="red", ubicacion="192.168.1.50:9100")
"""
from __future__ import annotations
import io
import logging
import struct
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("spj.escpos")

# ══════════════════════════════════════════════════════════════════════════════
#  Constantes ESC/POS
# ══════════════════════════════════════════════════════════════════════════════

ESC = b'\x1b'
GS  = b'\x1d'
FS  = b'\x1c'

# Inicialización
INIT          = ESC + b'@'

# Alineación
ALIGN_LEFT    = ESC + b'a\x00'
ALIGN_CENTER  = ESC + b'a\x01'
ALIGN_RIGHT   = ESC + b'a\x02'

# Estilo de texto
BOLD_ON       = ESC + b'E\x01'
BOLD_OFF      = ESC + b'E\x00'
DOUBLE_H_ON   = ESC + b'!\x10'    # Doble altura
DOUBLE_W_ON   = ESC + b'!\x20'    # Doble ancho
DOUBLE_HW_ON  = ESC + b'!\x30'    # Doble alto + ancho
NORMAL        = ESC + b'!\x00'    # Reset tamaño

# Underline
UNDERLINE_ON  = ESC + b'-\x01'
UNDERLINE_OFF = ESC + b'-\x00'

# Line spacing
LINE_SPACING_DEFAULT = ESC + b'2'
LINE_SPACING_SET     = ESC + b'3'   # + 1 byte (n dots)

# Paper
FEED_N        = ESC + b'd'        # + 1 byte (n lines)
CUT_FULL      = GS + b'V\x00'
CUT_PARTIAL   = GS + b'V\x42\x00'

# Chars por línea según ancho de papel
CHARS_BY_WIDTH = {
    58: 32,    # 58mm → 32 chars
    72: 42,    # 72mm → 42 chars  (CUSTOM)
    80: 48,    # 80mm → 48 chars
}


# ══════════════════════════════════════════════════════════════════════════════
#  Renderer principal
# ══════════════════════════════════════════════════════════════════════════════

class TicketESCPOSRenderer:
    """Genera bytes ESC/POS a partir de ticket_data del ERP."""

    def __init__(self, paper_width_mm: int = 80, encoding: str = "utf-8"):
        self.paper_width = paper_width_mm
        self.encoding = encoding
        self.chars_per_line = CHARS_BY_WIDTH.get(paper_width_mm, 48)

    # ── API principal ─────────────────────────────────────────────────────────

    def render(self, ticket_data: Dict[str, Any],
               logo_b64: str = "", qr_content: str = "") -> bytes:
        """
        Genera bytes ESC/POS completos listos para enviar a la impresora.

        Args:
            ticket_data: Mismo dict que usa generar_html_ticket()
            logo_b64: Logo en base64 (data:image/png;base64,... o raw b64)
            qr_content: Contenido para código QR (folio, URL, etc.)

        Returns:
            bytes listos para enviar via socket/serial/USB
        """
        buf = bytearray()
        w = self.chars_per_line

        # 1. Init
        buf += INIT

        # 2. Logo
        if logo_b64:
            logo_bytes = self._render_logo(logo_b64)
            if logo_bytes:
                buf += ALIGN_CENTER
                buf += logo_bytes
                buf += b'\n'

        # 3. Header: empresa
        empresa = ticket_data.get('empresa', 'SPJ POS')
        empresa_dir = ticket_data.get('direccion', '')
        empresa_tel = ticket_data.get('telefono', '')

        buf += ALIGN_CENTER
        buf += DOUBLE_HW_ON
        buf += self._text(empresa)
        buf += NORMAL
        if empresa_dir:
            buf += self._text(empresa_dir)
        if empresa_tel:
            buf += self._text(f"Tel: {empresa_tel}")

        # 4. Info de venta
        buf += self._separator(w)
        buf += ALIGN_LEFT

        folio  = ticket_data.get('folio', '')
        fecha  = ticket_data.get('fecha', '')
        cajero = ticket_data.get('cajero', '')
        cliente = ticket_data.get('cliente', 'Público General')

        buf += BOLD_ON
        buf += self._text(f"Folio: {folio}")
        buf += BOLD_OFF
        buf += self._text(f"Fecha: {fecha}")
        buf += self._text(f"Cajero: {cajero}")
        buf += self._text(f"Cliente: {cliente}")

        # 5. Items
        buf += self._separator(w)
        buf += BOLD_ON
        buf += self._columns("PRODUCTO", "CANT", "TOTAL", w)
        buf += BOLD_OFF
        buf += self._separator(w, char='-')

        items = ticket_data.get('items', [])
        for item in items:
            nombre = str(item.get('nombre', ''))
            cant   = float(item.get('cantidad', item.get('qty', 0)))
            unidad = str(item.get('unidad', 'pz'))
            precio = float(item.get('precio_unitario', item.get('unit_price', 0)))
            total_it = float(item.get('total', item.get('subtotal', cant * precio)))

            cant_str = f"{cant:.2f}{unidad}"
            total_str = f"${total_it:.2f}"

            # Si el nombre es largo, ponerlo en su propia línea
            col_nombre = w - 18  # espacio para cant + total
            if len(nombre) > col_nombre:
                buf += self._text(nombre)
                buf += self._columns("", cant_str, total_str, w)
            else:
                buf += self._columns(nombre, cant_str, total_str, w)

        # 6. Totales
        buf += self._separator(w)
        totales = ticket_data.get('totales', {})
        subtotal    = float(totales.get('subtotal', 0))
        descuento   = float(totales.get('descuento', 0))
        total_final = float(totales.get('total_final', subtotal))

        buf += ALIGN_RIGHT
        if descuento > 0:
            buf += self._text(f"Subtotal: ${subtotal:.2f}")
            buf += self._text(f"Descuento: -${descuento:.2f}")
        buf += BOLD_ON + DOUBLE_H_ON
        buf += self._text(f"TOTAL: ${total_final:.2f}")
        buf += NORMAL + BOLD_OFF

        # 7. Pago
        pago = ticket_data.get('pago', {})
        forma_pago = pago.get('forma_pago', '')
        if forma_pago:
            buf += ALIGN_LEFT
            buf += self._separator(w, char='-')
            buf += self._text(f"Forma de pago: {forma_pago}")
            if forma_pago.lower() == 'efectivo':
                recibido = float(pago.get('efectivo_recibido', total_final))
                cambio = float(pago.get('cambio', 0))
                buf += self._text(f"Recibido: ${recibido:.2f}")
                buf += self._text(f"Cambio: ${cambio:.2f}")

        # 8. Puntos fidelidad
        puntos_ganados = ticket_data.get('puntos_ganados', 0)
        if puntos_ganados:
            buf += self._separator(w, char='-')
            buf += ALIGN_CENTER
            buf += self._text(f"Puntos ganados: +{puntos_ganados}")
            puntos_total = ticket_data.get('puntos_totales', 0)
            if puntos_total:
                buf += self._text(f"Saldo total: {puntos_total} puntos")

        # 9. QR code
        if qr_content:
            qr_bytes = self._render_qr(qr_content)
            if qr_bytes:
                buf += ALIGN_CENTER
                buf += qr_bytes

        # 10. Footer
        buf += self._separator(w)
        buf += ALIGN_CENTER
        msg = ticket_data.get('mensaje_psicologico', '¡Gracias por su compra!')
        buf += self._text(msg)
        buf += self._text("")

        # 11. Feed + Cut
        buf += FEED_N + b'\x04'   # 4 líneas de avance
        buf += CUT_PARTIAL

        return bytes(buf)

    # ── Helpers de texto ──────────────────────────────────────────────────────

    def _text(self, text: str) -> bytes:
        """Línea de texto con newline."""
        return (text + '\n').encode(self.encoding, errors='replace')

    def _separator(self, width: int, char: str = '=') -> bytes:
        return (char * width + '\n').encode(self.encoding)

    def _columns(self, left: str, middle: str, right: str, width: int) -> bytes:
        """Alinea 3 columnas en una línea de ancho fijo."""
        mid_w = max(8, len(middle) + 1)
        right_w = max(9, len(right) + 1)
        left_w = width - mid_w - right_w

        left_str = left[:left_w].ljust(left_w)
        mid_str = middle[:mid_w].rjust(mid_w)
        right_str = right[:right_w].rjust(right_w)

        line = f"{left_str}{mid_str}{right_str}\n"
        return line.encode(self.encoding, errors='replace')

    # ── Logo: base64 → ESC/POS bitmap ─────────────────────────────────────────

    def _render_logo(self, logo_b64: str) -> Optional[bytes]:
        """Convierte base64 image a comandos ESC/POS de bitmap."""
        try:
            from PIL import Image
            import base64

            # Limpiar prefix data:image/...;base64,
            if ',' in logo_b64:
                logo_b64 = logo_b64.split(',', 1)[1]

            img_bytes = base64.b64decode(logo_b64)
            img = Image.open(io.BytesIO(img_bytes))

            # Convertir a blanco/negro
            img = img.convert('L')  # Grayscale

            # Escalar al ancho de la impresora (dots)
            # 80mm → ~384 dots, 58mm → ~384 dots (8 dots/mm)
            max_dots_w = (self.paper_width - 10) * 8  # margen 5mm por lado
            if img.width > max_dots_w:
                ratio = max_dots_w / img.width
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.LANCZOS)

            # Asegurar ancho múltiplo de 8
            if img.width % 8 != 0:
                new_w = img.width + (8 - img.width % 8)
                new_img = Image.new('L', (new_w, img.height), 255)
                new_img.paste(img, (0, 0))
                img = new_img

            # Convertir a bitmap 1-bit (negro = tinta, blanco = no tinta)
            img = img.point(lambda x: 0 if x < 128 else 255, '1')

            # Generar comandos ESC/POS para imagen
            return self._image_to_escpos_raster(img)

        except ImportError:
            logger.warning("PIL/Pillow no instalado — logo no se imprimirá. "
                           "Instalar: pip install Pillow")
            return None
        except Exception as e:
            logger.warning("Error renderizando logo: %s", e)
            return None

    def _image_to_escpos_raster(self, img) -> bytes:
        """
        Convierte PIL Image (modo '1') a comandos GS v 0 (raster bit image).
        Compatible con la mayoría de impresoras térmicas modernas.
        """
        width_bytes = img.width // 8
        height = img.height
        pixels = img.tobytes()

        # GS v 0 — Print raster bit image
        # GS v 0 m xL xH yL yH d1...dk
        # m = 0 (normal), 1 (double width), 2 (double height), 3 (double both)
        buf = bytearray()
        buf += GS + b'v0'
        buf += b'\x00'  # m = normal
        buf += struct.pack('<H', width_bytes)  # xL, xH
        buf += struct.pack('<H', height)       # yL, yH
        buf += pixels

        return bytes(buf)

    # ── QR Code como bitmap ───────────────────────────────────────────────────

    def _render_qr(self, content: str) -> Optional[bytes]:
        """Genera QR code como bitmap ESC/POS."""
        try:
            import qrcode
            from PIL import Image

            qr = qrcode.QRCode(version=1, box_size=4, border=2,
                                error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img = img.convert('L')

            # Escalar si es muy grande
            max_w = (self.paper_width - 20) * 8
            if img.width > max_w:
                ratio = max_w / img.width
                img = img.resize(
                    (int(img.width * ratio), int(img.height * ratio)),
                    Image.LANCZOS)

            # Alinear a múltiplo de 8
            if img.width % 8 != 0:
                new_w = img.width + (8 - img.width % 8)
                new_img = Image.new('L', (new_w, img.height), 255)
                new_img.paste(img, (0, 0))
                img = new_img

            img = img.point(lambda x: 0 if x < 128 else 255, '1')
            return self._image_to_escpos_raster(img)

        except ImportError:
            logger.debug("qrcode/Pillow no disponible para QR en ticket")
            return None
        except Exception as e:
            logger.debug("QR render error: %s", e)
            return None

    # ── Envío a impresora ─────────────────────────────────────────────────────

    def send(self, data: bytes, tipo: str = "",
             ubicacion: str = "", cfg: Dict = None) -> bool:
        """
        Envía bytes ESC/POS a la impresora.

        Args:
            data: Bytes generados por render()
            tipo: "red"/"tcp", "serial"/"com", "usb"/"win32"
            ubicacion: IP:puerto, COM port, o nombre de impresora Windows
            cfg: Dict de config (tipo, ubicacion, tipo_idx) — alternativa a args
        """
        if cfg:
            tipo = str(cfg.get('tipo', tipo)).lower()
            ubicacion = str(cfg.get('ubicacion', ubicacion))
            tipo_idx = int(cfg.get('tipo_idx', -1))
            if tipo_idx == 0:
                tipo = "win32"
            elif tipo_idx == 2:
                tipo = "red"

        tipo = tipo.lower()

        try:
            if 'win32' in tipo or 'usb' in tipo:
                return self._send_win32(data, ubicacion)
            elif 'red' in tipo or 'tcp' in tipo or ':' in ubicacion:
                return self._send_network(data, ubicacion)
            elif 'serial' in tipo or 'com' in tipo.lower():
                return self._send_serial(data, ubicacion)
            else:
                # Intentar detectar
                if ':' in ubicacion and ubicacion[0].isdigit():
                    return self._send_network(data, ubicacion)
                elif ubicacion.upper().startswith('COM'):
                    return self._send_serial(data, ubicacion)
                else:
                    return self._send_win32(data, ubicacion)
        except Exception as e:
            logger.error("Error enviando a impresora (%s, %s): %s",
                         tipo, ubicacion, e)
            return False

    def _send_network(self, data: bytes, ubicacion: str) -> bool:
        """Envía via TCP/IP (impresora en red)."""
        import socket
        parts = ubicacion.split(':')
        ip = parts[0].strip()
        port = int(parts[1]) if len(parts) > 1 else 9100
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, port))
        s.sendall(data)
        s.close()
        logger.info("Ticket enviado via red: %s:%d (%d bytes)", ip, port, len(data))
        return True

    def _send_serial(self, data: bytes, ubicacion: str) -> bool:
        """Envía via puerto serial (COM)."""
        import serial
        with serial.Serial(ubicacion, 9600, timeout=3) as sp:
            sp.write(data)
        logger.info("Ticket enviado via serial: %s (%d bytes)", ubicacion, len(data))
        return True

    def _send_win32(self, data: bytes, ubicacion: str) -> bool:
        """Envía via Win32 print spooler (USB en Windows)."""
        import win32print
        printer_name = ubicacion or win32print.GetDefaultPrinter()
        hp = win32print.OpenPrinter(printer_name)
        try:
            hj = win32print.StartDocPrinter(hp, 1, ("SPJ Ticket", None, "RAW"))
            win32print.StartPagePrinter(hp)
            win32print.WritePrinter(hp, data)
            win32print.EndPagePrinter(hp)
            win32print.EndDocPrinter(hp)
        finally:
            win32print.ClosePrinter(hp)
        logger.info("Ticket enviado via Win32: %s (%d bytes)", printer_name, len(data))
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  Helper para usar desde ventas.py
# ══════════════════════════════════════════════════════════════════════════════

def render_and_print_ticket(ticket_data: Dict[str, Any],
                            printer_cfg: Dict = None,
                            db_conn=None) -> bool:
    """
    Función de conveniencia: renderiza + imprime en un paso.
    Lee logo y config de la BD automáticamente.

    Usage:
        from core.ticket_escpos_renderer import render_and_print_ticket
        render_and_print_ticket(ticket_data, printer_cfg, self.container.db)
    """
    logo_b64 = ""
    qr_content = ""
    paper_w = 80

    if db_conn:
        try:
            def _cfg(k, d=""):
                r = db_conn.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return r[0] if r and r[0] else d

            logo_b64 = _cfg('ticket_logo_b64', '')
            paper_w = int(_cfg('ticket_paper_width', '80'))

            if _cfg('ticket_qr_enabled', '0') == '1':
                qr_content = _cfg('ticket_qr_url', '') or ticket_data.get('folio', '')

            # Enriquecer ticket_data con datos de empresa
            ticket_data.setdefault('empresa', _cfg('nombre_empresa', 'SPJ POS'))
            ticket_data.setdefault('direccion', _cfg('direccion', ''))
            ticket_data.setdefault('telefono', _cfg('telefono_empresa', ''))
        except Exception as e:
            logger.debug("render_and_print_ticket config: %s", e)

    renderer = TicketESCPOSRenderer(paper_width_mm=paper_w)
    data = renderer.render(ticket_data, logo_b64=logo_b64, qr_content=qr_content)

    if not printer_cfg:
        return False

    return renderer.send(data, cfg=printer_cfg)
