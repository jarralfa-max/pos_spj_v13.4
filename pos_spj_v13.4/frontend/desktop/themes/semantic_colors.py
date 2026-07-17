"""Semantic color tokens (FASE DS-1).

Tokens carry *meaning*, not visual names. They derive from the JUANIS brand
palette but are tuned for WCAG AA contrast — a color is never approved just for
belonging to the brand. Two themes: ``Light`` and ``Dark``. ``ChartPalette``
adds accessible categorical/sequential colors for multi-series charts.
"""

from __future__ import annotations

from frontend.desktop.themes.brand_palette import BrandColors, BrandScale


class Light:
    # brand anchors
    PRIMARY = BrandColors.FOREST_GREEN
    ACCENT = BrandColors.PREMIUM_GOLD
    DANGER = BrandColors.TRADITIONAL_RED
    WARM_SURFACE = BrandColors.SOFT_CREAM
    EARTH_NEUTRAL = BrandColors.EARTH_BROWN

    # primary (green)
    PRIMARY_DEFAULT = BrandColors.FOREST_GREEN
    PRIMARY_HOVER = BrandScale.GREEN_600
    PRIMARY_PRESSED = BrandScale.GREEN_700
    PRIMARY_SUBTLE = BrandScale.GREEN_50
    PRIMARY_BORDER = BrandScale.GREEN_200

    # accent (gold) — ACCENT_TEXT is the legible-on-light variant
    ACCENT_DEFAULT = BrandColors.PREMIUM_GOLD
    ACCENT_HOVER = BrandScale.GOLD_600
    ACCENT_PRESSED = BrandScale.GOLD_700
    ACCENT_SUBTLE = BrandScale.GOLD_50
    ACCENT_TEXT = BrandScale.GOLD_800

    # success (green, distinct from brand primary)
    SUCCESS_DEFAULT = "#2F7A44"
    SUCCESS_SUBTLE = "#E3F1E6"
    SUCCESS_BORDER = "#8FC7A0"

    # warning (amber-earth, NOT gold — gold fails AA as text)
    WARNING_DEFAULT = "#9A5B12"
    WARNING_SUBTLE = "#FBEED8"
    WARNING_BORDER = "#E0B074"

    # danger (red)
    DANGER_DEFAULT = BrandColors.TRADITIONAL_RED
    DANGER_HOVER = BrandScale.RED_600
    DANGER_PRESSED = BrandScale.RED_700
    DANGER_SUBTLE = "#F7E3E2"
    DANGER_BORDER = "#D89B99"

    # info (muted teal, harmonizes with the earth palette)
    INFO_DEFAULT = "#1F6470"
    INFO_SUBTLE = "#DEEEF1"
    INFO_BORDER = "#8FBFC7"

    # surfaces
    BACKGROUND = "#FAF6EF"
    SURFACE = "#FFFFFF"
    SURFACE_ELEVATED = "#FFFFFF"
    SURFACE_MUTED = "#F3EBDD"

    # text
    TEXT_PRIMARY = "#1A241E"
    TEXT_SECONDARY = "#544027"
    TEXT_MUTED = "#6B5943"
    TEXT_INVERSE = "#FBF7F0"
    TEXT_DISABLED = "#9C8F7B"

    # borders
    BORDER_DEFAULT = "#DAD0C1"
    BORDER_SUBTLE = "#E9E1D4"
    BORDER_STRONG = "#8A7A5C"

    # interaction
    FOCUS_RING = BrandColors.FOREST_GREEN
    SELECTION = BrandScale.GREEN_100
    DISABLED_BACKGROUND = "#F0EAE0"
    DISABLED_BORDER = "#DDD3C4"

    # tooltip (dark surface + light text)
    TOOLTIP_BACKGROUND = BrandScale.GREEN_800
    TOOLTIP_TEXT = "#F6F0E4"


class Dark:
    PRIMARY = BrandColors.FOREST_GREEN
    ACCENT = BrandColors.PREMIUM_GOLD
    DANGER = BrandColors.TRADITIONAL_RED
    WARM_SURFACE = BrandColors.SOFT_CREAM
    EARTH_NEUTRAL = BrandColors.EARTH_BROWN

    # primary (lightened green for contrast on dark)
    PRIMARY_DEFAULT = "#5AA377"
    PRIMARY_HOVER = "#6BB588"
    PRIMARY_PRESSED = "#4C8F68"
    PRIMARY_SUBTLE = "#1B2C24"
    PRIMARY_BORDER = "#3B5A49"

    # accent (gold adjusted for dark)
    ACCENT_DEFAULT = "#D8B879"
    ACCENT_HOVER = "#E4C88E"
    ACCENT_PRESSED = "#C4A464"
    ACCENT_SUBTLE = "#2C2618"
    ACCENT_TEXT = "#E1C48A"

    SUCCESS_DEFAULT = "#5CB878"
    SUCCESS_SUBTLE = "#17281D"
    SUCCESS_BORDER = "#3E6B4E"

    WARNING_DEFAULT = "#E0A45A"
    WARNING_SUBTLE = "#2C2214"
    WARNING_BORDER = "#6B5330"

    DANGER_DEFAULT = "#E0716D"
    DANGER_HOVER = "#EA8783"
    DANGER_PRESSED = "#C85B57"
    DANGER_SUBTLE = "#2C1917"
    DANGER_BORDER = "#6B3936"

    INFO_DEFAULT = "#5FB2C0"
    INFO_SUBTLE = "#152628"
    INFO_BORDER = "#356068"

    # surfaces (near-black green → elevated)
    BACKGROUND = "#0F1512"
    SURFACE = "#182420"
    SURFACE_ELEVATED = "#22322B"
    SURFACE_MUTED = "#131D19"

    # text
    TEXT_PRIMARY = "#F1E9DA"
    TEXT_SECONDARY = "#C8BCA6"
    TEXT_MUTED = "#9E947F"
    TEXT_INVERSE = "#182420"
    TEXT_DISABLED = "#6C6555"

    BORDER_DEFAULT = "#3A4A42"
    BORDER_SUBTLE = "#2A3831"
    BORDER_STRONG = "#788D80"

    FOCUS_RING = "#D8B879"
    SELECTION = "#233A2E"
    DISABLED_BACKGROUND = "#1C2622"
    DISABLED_BORDER = "#33403A"

    TOOLTIP_BACKGROUND = "#0B100D"
    TOOLTIP_TEXT = "#F1E9DA"


class SemanticColors:
    """Facade: ``SemanticColors.for_theme("dark")`` → the token namespace."""

    light = Light
    dark = Dark

    @classmethod
    def for_theme(cls, theme: str):
        return cls.dark if str(theme).lower() == "dark" else cls.light


class ChartPalette:
    """Accessible chart colors. Categorical series stay distinguishable; status
    colors keep the same meaning across every chart. Derived from JUANIS but
    extended with harmonizing hues so many series remain legible.
    """

    CATEGORICAL = (
        BrandColors.FOREST_GREEN,
        BrandColors.PREMIUM_GOLD,
        BrandColors.TRADITIONAL_RED,
        "#2A6F7A",   # teal
        BrandColors.EARTH_BROWN,
        "#4C8A66",   # sage green
        "#8A6D2F",   # dark gold
        "#7A4E7A",   # muted plum
    )
    SEQUENTIAL = (
        BrandScale.GREEN_100, BrandScale.GREEN_300, BrandScale.GREEN_500,
        BrandScale.GREEN_700, BrandScale.GREEN_900,
    )
    DIVERGING = (
        BrandScale.RED_600, BrandScale.RED_300, "#EFE7D6",
        BrandScale.GREEN_300, BrandScale.GREEN_600,
    )
    STATUS = {
        "success": "#2F7A44",
        "warning": "#9A5B12",
        "danger": BrandColors.TRADITIONAL_RED,
        "info": "#1F6470",
        "neutral": BrandColors.EARTH_BROWN,
    }
    FINANCIAL = (BrandColors.FOREST_GREEN, BrandColors.TRADITIONAL_RED,
                 BrandColors.PREMIUM_GOLD)
    INVENTORY = ("#2A6F7A", BrandScale.GREEN_500, BrandColors.PREMIUM_GOLD,
                 BrandColors.TRADITIONAL_RED)
    PRODUCTION = (BrandColors.EARTH_BROWN, BrandColors.PREMIUM_GOLD,
                  BrandColors.FOREST_GREEN)
