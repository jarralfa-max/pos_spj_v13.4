
# delivery/mapas_qr.py — SPJ POS v12
"""
Módulo dedicado para QR de mapas en tickets de delivery.
Genera:
  - URL de mapa (Google Maps / OpenStreetMap)
  - Imagen QR del mapa incrustable en tickets ESC/POS y etiquetas
  - QR con coordenadas GPS en formato geo:lat,lng
"""
from __future__ import annotations
import io, logging
from urllib.parse import quote
from typing import Tuple

logger = logging.getLogger("spj.delivery.mapas_qr")

GOOGLE_MAPS   = "https://maps.google.com/?q={}"
OPENSTREET    = "https://www.openstreetmap.org/?mlat={lat}&mlon={lng}&zoom=16"
GEO_URI       = "geo:{lat},{lng}"
WAZE          = "https://waze.com/ul?ll={lat},{lng}&navigate=yes"


class MapasQR:
    """Genera QR de mapa para tickets de delivery."""

    def __init__(self, conn=None):
        self.conn = conn

    # ── URLs de mapa ───────────────────────────────────────────────
    @staticmethod
    def url_google_maps(direccion: str = None,
                        lat: float = None, lng: float = None) -> str:
        if lat and lng:
            return GOOGLE_MAPS.format(f"{lat},{lng}")
        if direccion:
            return GOOGLE_MAPS.format(quote(direccion))
        return ""

    @staticmethod
    def url_openstreet(lat: float, lng: float) -> str:
        return OPENSTREET.format(lat=lat, lng=lng)

    @staticmethod
    def url_waze(lat: float, lng: float) -> str:
        return WAZE.format(lat=lat, lng=lng)

    @staticmethod
    def geo_uri(lat: float, lng: float) -> str:
        """geo: URI estándar — abre en cualquier app de mapas."""
        return GEO_URI.format(lat=lat, lng=lng)

    # ── Imagen QR del mapa ─────────────────────────────────────────
    def imagen_qr_mapa(self, direccion: str = None,
                       lat: float = None, lng: float = None,
                       modo: str = "google",
                       size: int = 200) -> bytes:
        """
        Genera imagen PNG del QR que apunta al mapa.
        modo: 'google' | 'openstreet' | 'waze' | 'geo'
        """
        url = self._get_url(modo, direccion, lat, lng)
        if not url:
            return b""
        return self._render_qr(url, size)

    def imagen_qr_mapa_b64(self, direccion: str = None,
                            lat: float = None, lng: float = None,
                            modo: str = "google") -> str:
        """Retorna imagen QR en base64 para HTML."""
        import base64
        png = self.imagen_qr_mapa(direccion, lat, lng, modo)
        if not png:
            return ""
        return "data:image/png;base64," + base64.b64encode(png).decode()

    def _get_url(self, modo: str, direccion: str,
                 lat: float, lng: float) -> str:
        if modo == "google":
            return self.url_google_maps(direccion, lat, lng)
        elif modo == "openstreet" and lat and lng:
            return self.url_openstreet(lat, lng)
        elif modo == "waze" and lat and lng:
            return self.url_waze(lat, lng)
        elif modo == "geo" and lat and lng:
            return self.geo_uri(lat, lng)
        elif direccion:
            return self.url_google_maps(direccion)
        return ""

    def _render_qr(self, contenido: str, size: int) -> bytes:
        try:
            import qrcode
            qr  = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8, border=2)
            qr.add_data(contenido)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except ImportError:
            return self._svg_qr(contenido, size)
        except Exception as e:
            logger.error("render_qr: %s", e)
            return b""

    @staticmethod
    def _svg_qr(texto: str, size: int) -> bytes:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
               f'width="{size}" height="{size}">'
               f'<rect width="{size}" height="{size}" fill="white"/>'
               f'<rect x="8" y="8" width="60" height="60" fill="none" '
               f'stroke="black" stroke-width="6"/>'
               f'<rect x="22" y="22" width="32" height="32" fill="black"/>'
               f'<text x="{size//2}" y="{size-8}" text-anchor="middle" '
               f'font-size="9">{texto[:28]}</text></svg>')
        return svg.encode()

    # ── ESC/POS: imprimir QR de mapa en ticket ────────────────────
    def escpos_qr_mapa(self, direccion: str = None,
                       lat: float = None, lng: float = None) -> bytes:
        """
        Secuencia ESC/POS para imprimir QR de mapa en impresora de tickets.
        Compatible con impresoras Epson TM-series y clones.
        """
        url = self._get_url("google", direccion, lat, lng)
        if not url:
            return b""
        # GS ( k — 2D barcode (QR Code)
        # Formato: función 165 (store data) + función 167 (print)
        data      = url.encode("utf-8")
        data_len  = len(data) + 3
        pL        = data_len & 0xFF
        pH        = (data_len >> 8) & 0xFF
        cmd  = bytes([
            0x1D, 0x28, 0x6B,          # GS ( k
            pL, pH,                     # pL pH
            0x31,                       # cn = 49 (QR)
            0x50,                       # fn = 80 (store data)
            0x30,                       # m = 48
        ]) + data
        # Ajuste de módulo (tamaño): GS ( k 3 0 49 67 m
        size_cmd = bytes([0x1D,0x28,0x6B,0x03,0x00,0x31,0x43,0x06])
        # Nivel de corrección: M
        ecl_cmd  = bytes([0x1D,0x28,0x6B,0x03,0x00,0x31,0x45,0x4D])
        # Imprimir QR: GS ( k 3 0 49 81 48
        print_cmd= bytes([0x1D,0x28,0x6B,0x03,0x00,0x31,0x51,0x30])
        return size_cmd + ecl_cmd + cmd + print_cmd

    # ── Datos de repartidor en BD ──────────────────────────────────
    def get_coords_repartidor(self, repartidor_id: int) -> Tuple[float, float] | None:
        if not self.conn:
            return None
        try:
            row = self.conn.execute(
                "SELECT lat, lng FROM driver_locations WHERE chofer_id=?",
                (repartidor_id,)).fetchone()
            return (row[0], row[1]) if row else None
        except Exception:
            return None

    def qr_seguimiento_pedido(self, pedido_id: int,
                               base_url: str = "http://localhost:8769") -> str:
        """URL de seguimiento del pedido para el QR del ticket cliente."""
        return f"{base_url}/seguimiento?pedido={pedido_id}"

    def imagen_qr_seguimiento(self, pedido_id: int,
                               base_url: str = "http://localhost:8769") -> bytes:
        url = self.qr_seguimiento_pedido(pedido_id, base_url)
        return self._render_qr(url, 200)
