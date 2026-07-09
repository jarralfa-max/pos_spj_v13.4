"""Utilidades de imagen para el logo del ticket.

quitar_fondo(): convierte el fondo sólido de un logo (típicamente blanco) en
transparencia y devuelve un PNG con canal alfa. Reglas:
- No falla nunca: si la imagen no se puede decodificar (p.ej. SVG) devuelve los
  bytes originales sin cambios.
- El color de fondo se infiere de las esquinas (el más frecuente).
- Se trabaja a tamaño acotado (los logos de ticket son pequeños).
"""
from __future__ import annotations

import io
import logging
from collections import Counter

logger = logging.getLogger("spj.logo_utils")


def quitar_fondo(data: bytes, tolerancia: int = 30, max_lado: int = 512) -> bytes:
    """Devuelve un PNG (bytes) con el fondo hecho transparente.

    tolerancia: distancia por canal (0-255) para considerar un pixel "fondo".
    max_lado: se reduce la imagen si su lado mayor lo excede (logos pequeños).
    """
    try:
        from PIL import Image
    except Exception as exc:  # Pillow no disponible → sin cambios
        logger.warning("Pillow no disponible; no se puede quitar fondo: %s", exc)
        return data

    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as exc:  # formato no rasterizable (SVG, corrupto…)
        logger.debug("quitar_fondo: imagen no decodificable (%s); se deja igual", exc)
        return data

    if max(img.size) > max_lado:
        img.thumbnail((max_lado, max_lado))

    w, h = img.size
    if w == 0 or h == 0:
        return data

    px = img.load()
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    br, bg, bb = Counter((c[0], c[1], c[2]) for c in corners).most_common(1)[0][0]

    tol = int(tolerancia)

    def _es_fondo(r: int, g: int, b: int) -> bool:
        return abs(r - br) <= tol and abs(g - bg) <= tol and abs(b - bb) <= tol

    # get_flattened_data() en Pillow ≥14, getdata() en versiones previas.
    _pixels = getattr(img, "get_flattened_data", img.getdata)()
    nueva = [
        (r, g, b, 0) if _es_fondo(r, g, b) else (r, g, b, a)
        for (r, g, b, a) in _pixels
    ]
    img.putdata(nueva)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()
