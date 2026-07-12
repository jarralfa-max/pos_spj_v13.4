"""Utilidades de imagen para el logo del ticket.

quitar_fondo(): hace transparente el fondo de un logo y devuelve un PNG con canal
alfa. Usa relleno por inundación (flood-fill) desde los bordes, de modo que sólo
se vuelve transparente el fondo CONECTADO al borde. Así se preserva cualquier
región interior del mismo color que el fondo (p.ej. el cuerpo blanco de un logo
sobre fondo blanco/gris claro), que un simple emparejado por color eliminaría.

Reglas:
- No falla nunca: si la imagen no se puede decodificar (p.ej. SVG) devuelve los
  bytes originales sin cambios.
- Trabaja a resolución acotada (logos pequeños).
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger("spj.logo_utils")

# Color sentinela improbable en un logo (verde muy saturado atípico).
_SENT = (1, 254, 3)


def quitar_fondo(data: bytes, tolerancia: int = 32, max_lado: int = 1024) -> bytes:
    """Devuelve un PNG (bytes) con el fondo (conectado al borde) hecho transparente.

    tolerancia: diferencia máxima de color para considerar un pixel parte del fondo.
    max_lado: se reduce la imagen si su lado mayor lo excede.
    """
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:  # Pillow no disponible → sin cambios
        logger.warning("Pillow no disponible; no se puede quitar fondo: %s", exc)
        return data

    try:
        base = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:  # formato no rasterizable (SVG, corrupto…)
        logger.debug("quitar_fondo: imagen no decodificable (%s); se deja igual", exc)
        return data

    if max(base.size) > max_lado:
        base.thumbnail((max_lado, max_lado))

    w, h = base.size
    if w == 0 or h == 0:
        return data

    # Inundar desde varios puntos del borde: sólo el fondo tocando el borde se marca.
    flood = base.copy()
    seeds = [
        (0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
        (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2),
    ]
    for seed in seeds:
        try:
            ImageDraw.floodfill(flood, seed, _SENT, thresh=int(tolerancia))
        except Exception:
            pass

    rgba = base.convert("RGBA")
    _flood_px = getattr(flood, "get_flattened_data", flood.getdata)()
    _rgba_px = getattr(rgba, "get_flattened_data", rgba.getdata)()
    nueva = [
        (r, g, b, 0) if fp == _SENT else (r, g, b, a)
        for fp, (r, g, b, a) in zip(_flood_px, _rgba_px)
    ]
    rgba.putdata(nueva)

    out = io.BytesIO()
    rgba.save(out, format="PNG")
    return out.getvalue()
