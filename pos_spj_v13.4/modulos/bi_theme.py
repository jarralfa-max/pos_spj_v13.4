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

# Superficies por tema (derivadas de los tokens neutrales). El dashboard es
# theme-aware: la capa de presentación elige la superficie según el tema activo.
SURFACES = {
    "dark": {
        "bg": _N.DARK_BG, "card": _N.DARK_CARD, "border": _N.DARK_BORDER,
        "text": _N.DARK_TEXT, "muted": _N.DARK_TEXT_SEC, "grid": _N.SLATE_700,
    },
    "light": {
        "bg": _N.WHITE, "card": _N.SLATE_50, "border": _N.SLATE_200,
        "text": _N.SLATE_800, "muted": _N.SLATE_500, "grid": _N.SLATE_200,
    },
}


def normalize_theme(theme: str) -> str:
    """Normaliza cualquier etiqueta de tema a 'dark' | 'light'."""
    t = str(theme or "").strip().lower()
    if t in ("dark", "oscuro", "night", "noche"):
        return "dark"
    if t in ("light", "claro", "day", "dia", "día"):
        return "light"
    return "dark"


def surface(theme: str = "dark") -> dict:
    """Devuelve la paleta de superficie (bg/card/border/text/muted/grid)."""
    return SURFACES[normalize_theme(theme)]


# Compat: constantes de superficie oscura (por defecto).
BG = SURFACES["dark"]["bg"]
CARD = SURFACES["dark"]["card"]
BORDER = SURFACES["dark"]["border"]
TEXT = SURFACES["dark"]["text"]
MUTED = SURFACES["dark"]["muted"]
GRID = SURFACES["dark"]["grid"]

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
