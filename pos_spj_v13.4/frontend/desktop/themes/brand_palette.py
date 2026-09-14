"""Official JUANIS brand identity palette (FASE DS-1).

These six colors are the brand identity — not a direct mapping to every
functional state. Semantic tokens (``semantic_colors.py``) derive accessible
variants from these bases. Only the theme layer may hold explicit colors.
"""

from __future__ import annotations

from frontend.desktop.themes.color_utils import darken, lighten


class BrandColors:
    """Official assets and these anchors define the JUANIS identity."""

    FOREST_GREEN = "#18372B"
    WHITE = "#FFFFFF"
    PREMIUM_GOLD = "#C6A15B"
    TRADITIONAL_RED = "#9D2927"
    CHARCOAL = "#252825"
    WARM_WHITE = "#F8F8F5"


class BrandScale:
    """Accessible tints/shades derived from the JUANIS bases.

    Suffix convention: 50 (lightest) → 900 (darkest). Derivations are computed
    (not hand-picked) so the whole scale stays internally consistent.
    """

    # Verde profundo
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

    # Rojo profundo
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

    # Dorado cálido
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

    # Blanco cálido
    WARM_WHITE_50 = lighten(BrandColors.WARM_WHITE, 0.60)
    WARM_WHITE_100 = lighten(BrandColors.WARM_WHITE, 0.42)
    WARM_WHITE_200 = lighten(BrandColors.WARM_WHITE, 0.24)
    WARM_WHITE_300 = lighten(BrandColors.WARM_WHITE, 0.10)
    WARM_WHITE_500 = BrandColors.WARM_WHITE
    WARM_WHITE_700 = darken(BrandColors.WARM_WHITE, 0.18)

    # Carbón
    CHARCOAL_50 = lighten(BrandColors.CHARCOAL, 0.88)
    CHARCOAL_100 = lighten(BrandColors.CHARCOAL, 0.76)
    CHARCOAL_200 = lighten(BrandColors.CHARCOAL, 0.56)
    CHARCOAL_300 = lighten(BrandColors.CHARCOAL, 0.36)
    CHARCOAL_400 = lighten(BrandColors.CHARCOAL, 0.16)
    CHARCOAL_500 = BrandColors.CHARCOAL
    CHARCOAL_600 = darken(BrandColors.CHARCOAL, 0.14)
    CHARCOAL_700 = darken(BrandColors.CHARCOAL, 0.28)
    CHARCOAL_800 = darken(BrandColors.CHARCOAL, 0.44)
    CHARCOAL_900 = darken(BrandColors.CHARCOAL, 0.60)
