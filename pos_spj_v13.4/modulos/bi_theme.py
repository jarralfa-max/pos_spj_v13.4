# -*- coding: utf-8 -*-
"""Paleta del módulo BI derivada de los design tokens globales.

Punto único de color para charts y vistas BI. NADA de hex hardcodeado aquí: todo
proviene de `modulos.design_tokens` (Colors / NeutralColors), de modo que si el
sistema cambia su paleta, el BI la hereda. Los servicios backend emiten *roles*
semánticos ("primary"/"secondary"/…) y la capa de presentación los resuelve a
color con `color()`.
"""
from __future__ import annotations

from modulos.design_tokens import Colors, NeutralColors

_N = NeutralColors()

# Superficie (tema oscuro estándar del módulo, tomado de los tokens neutrales).
BG = _N.DARK_BG          # fondo
CARD = _N.DARK_CARD      # tarjetas
BORDER = _N.DARK_BORDER  # bordes
TEXT = _N.DARK_TEXT      # texto principal
MUTED = _N.DARK_TEXT_SEC  # texto secundario
GRID = _N.SLATE_800      # líneas de eje

# Roles semánticos → color de token.
ROLE = {
    "primary": Colors.PRIMARY_BASE,
    "secondary": Colors.WARNING_HOVER,   # ámbar/dorado
    "accent": Colors.ACCENT_BASE,
    "positive": Colors.SUCCESS_HOVER,
    "negative": Colors.DANGER_HOVER,
    "info": Colors.INFO_HOVER,
    "neutral": _N.SLATE_500,
}

# Paleta categórica (donas / series múltiples) — derivada de los roles.
PALETTE = [ROLE["primary"], ROLE["secondary"], ROLE["positive"], ROLE["accent"],
           ROLE["negative"], ROLE["info"], ROLE["neutral"], _N.SLATE_400]

# Colores semánticos de estado (para deltas / alertas).
SEMANTIC = {"positive": ROLE["positive"], "negative": ROLE["negative"],
            "neutral": ROLE["neutral"]}


def color(role_or_hex: str) -> str:
    """Resuelve un rol semántico a color; si ya es hex (#...), lo devuelve igual."""
    s = str(role_or_hex or "")
    if s.startswith("#"):
        return s
    return ROLE.get(s, ROLE["primary"])
