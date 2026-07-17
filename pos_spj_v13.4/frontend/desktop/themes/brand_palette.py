"""Official JUANIS brand identity palette (FASE DS-1).

These five colors are the brand identity — not a direct mapping to every
functional state. Semantic tokens (``semantic_colors.py``) derive accessible
variants from these bases. Only the theme layer may hold explicit colors.
"""

from __future__ import annotations

from frontend.desktop.themes.color_utils import darken, lighten


class BrandColors:
    """The five canonical JUANIS colors."""

    FOREST_GREEN = "#1F3B2E"      # identidad principal / primario
    TRADITIONAL_RED = "#A52E2A"   # errores / acciones destructivas
    PREMIUM_GOLD = "#C7A254"      # acentos / detalles premium
    SOFT_CREAM = "#F2E6CF"        # fondos cálidos suaves
    EARTH_BROWN = "#6B4A2E"       # bordes cálidos / texto secundario


class BrandScale:
    """Accessible tints/shades derived from the JUANIS bases.

    Suffix convention: 50 (lightest) → 900 (darkest). Derivations are computed
    (not hand-picked) so the whole scale stays internally consistent.
    """

    # Verde Bosque
    GREEN_50 = lighten(BrandColors.FOREST_GREEN, 0.92)
    GREEN_100 = lighten(BrandColors.FOREST_GREEN, 0.84)
    GREEN_200 = lighten(BrandColors.FOREST_GREEN, 0.68)
    GREEN_300 = lighten(BrandColors.FOREST_GREEN, 0.50)
    GREEN_400 = lighten(BrandColors.FOREST_GREEN, 0.28)
    GREEN_500 = BrandColors.FOREST_GREEN
    GREEN_600 = darken(BrandColors.FOREST_GREEN, 0.12)
    GREEN_700 = darken(BrandColors.FOREST_GREEN, 0.24)
    GREEN_800 = darken(BrandColors.FOREST_GREEN, 0.40)
    GREEN_900 = darken(BrandColors.FOREST_GREEN, 0.55)

    # Rojo Tradicional
    RED_50 = lighten(BrandColors.TRADITIONAL_RED, 0.90)
    RED_100 = lighten(BrandColors.TRADITIONAL_RED, 0.80)
    RED_200 = lighten(BrandColors.TRADITIONAL_RED, 0.60)
    RED_300 = lighten(BrandColors.TRADITIONAL_RED, 0.40)
    RED_400 = lighten(BrandColors.TRADITIONAL_RED, 0.20)
    RED_500 = BrandColors.TRADITIONAL_RED
    RED_600 = darken(BrandColors.TRADITIONAL_RED, 0.12)
    RED_700 = darken(BrandColors.TRADITIONAL_RED, 0.24)
    RED_800 = darken(BrandColors.TRADITIONAL_RED, 0.38)
    RED_900 = darken(BrandColors.TRADITIONAL_RED, 0.52)

    # Dorado Premium
    GOLD_50 = lighten(BrandColors.PREMIUM_GOLD, 0.86)
    GOLD_100 = lighten(BrandColors.PREMIUM_GOLD, 0.74)
    GOLD_200 = lighten(BrandColors.PREMIUM_GOLD, 0.54)
    GOLD_300 = lighten(BrandColors.PREMIUM_GOLD, 0.32)
    GOLD_400 = lighten(BrandColors.PREMIUM_GOLD, 0.14)
    GOLD_500 = BrandColors.PREMIUM_GOLD
    GOLD_600 = darken(BrandColors.PREMIUM_GOLD, 0.18)
    GOLD_700 = darken(BrandColors.PREMIUM_GOLD, 0.34)   # dorado legible sobre blanco
    GOLD_800 = darken(BrandColors.PREMIUM_GOLD, 0.48)
    GOLD_900 = darken(BrandColors.PREMIUM_GOLD, 0.60)

    # Crema Suave
    CREAM_50 = lighten(BrandColors.SOFT_CREAM, 0.60)
    CREAM_100 = lighten(BrandColors.SOFT_CREAM, 0.42)
    CREAM_200 = lighten(BrandColors.SOFT_CREAM, 0.24)
    CREAM_300 = lighten(BrandColors.SOFT_CREAM, 0.10)
    CREAM_500 = BrandColors.SOFT_CREAM
    CREAM_700 = darken(BrandColors.SOFT_CREAM, 0.18)

    # Café Tierra
    BROWN_50 = lighten(BrandColors.EARTH_BROWN, 0.88)
    BROWN_100 = lighten(BrandColors.EARTH_BROWN, 0.76)
    BROWN_200 = lighten(BrandColors.EARTH_BROWN, 0.56)
    BROWN_300 = lighten(BrandColors.EARTH_BROWN, 0.36)
    BROWN_400 = lighten(BrandColors.EARTH_BROWN, 0.16)
    BROWN_500 = BrandColors.EARTH_BROWN
    BROWN_600 = darken(BrandColors.EARTH_BROWN, 0.14)
    BROWN_700 = darken(BrandColors.EARTH_BROWN, 0.28)
    BROWN_800 = darken(BrandColors.EARTH_BROWN, 0.44)
    BROWN_900 = darken(BrandColors.EARTH_BROWN, 0.60)
