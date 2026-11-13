"""Semantic color tokens (FASE DS-1).

Tokens carry *meaning*, not visual names. They derive from the JUANIS brand
palette but are tuned for WCAG AA contrast — a color is never approved just for
belonging to the brand. Two themes: ``Light`` and ``Dark``. ``ChartPalette``
adds accessible categorical/sequential colors for multi-series charts.
"""

from __future__ import annotations

from frontend.desktop.themes.brand_palette import BrandColors, BrandScale
from frontend.desktop.themes.color_utils import lighten, tone


class Light:
    # brand anchors
    PRIMARY = BrandColors.FOREST_GREEN
    ACCENT = BrandColors.PREMIUM_GOLD
    DANGER = BrandColors.TRADITIONAL_RED
    WARM_SURFACE = BrandColors.WARM_WHITE
    EARTH_NEUTRAL = BrandColors.CHARCOAL

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
    SUCCESS = SUCCESS_DEFAULT

    # warning (amber-earth, NOT gold — gold fails AA as text)
    WARNING_DEFAULT = "#9A5B12"
    WARNING_SUBTLE = "#FBEED8"
    WARNING_BORDER = "#E0B074"
    WARNING = WARNING_DEFAULT

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
    INFO = INFO_DEFAULT

    # surfaces
    BACKGROUND = BrandColors.WARM_WHITE
    SURFACE = BrandColors.WHITE
    SURFACE_ELEVATED = BrandColors.WHITE
    SURFACE_MUTED = BrandScale.WARM_WHITE_300

    # text
    TEXT_PRIMARY = BrandColors.CHARCOAL
    TEXT_SECONDARY = BrandScale.CHARCOAL_400
    # Helper text is 11 px: it must meet normal-text contrast on warm surfaces.
    TEXT_MUTED = lighten(BrandColors.CHARCOAL, 0.34)
    TEXT_INVERSE = BrandColors.WHITE
    TEXT_DISABLED = "#9C8F7B"

    # borders
    BORDER_DEFAULT = "#DAD0C1"
    BORDER_SUBTLE = "#E9E1D4"
    BORDER_STRONG = "#8A7A5C"
    BORDER = BORDER_DEFAULT
    INPUT_BORDER = BORDER_STRONG

    # interaction
    # Visible against both the primary green fill and the surrounding surface.
    FOCUS_RING = BrandScale.GOLD_600
    SELECTION = BrandScale.GREEN_100
    DISABLED_BACKGROUND = "#F0EAE0"
    DISABLED_BORDER = "#DDD3C4"

    # tooltip (dark surface + light text)
    TOOLTIP_BACKGROUND = BrandScale.GREEN_800
    TOOLTIP_TEXT = "#F6F0E4"


class Dark:
    """Dark theme derived from the JUANIS bases — no hand-written hex.

    ``tone(base, lightness, saturation)`` keeps the brand hue and lifts it for a
    dark surface; functional hues (success/warning/info) start from their Light
    counterpart so both themes share one meaning per hue.
    """

    # brand anchors, tuned for dark surfaces (raw brand fails contrast here)
    PRIMARY_DEFAULT = tone(BrandColors.FOREST_GREEN, 0.50, 0.29)
    ACCENT_DEFAULT = tone(BrandColors.PREMIUM_GOLD, 0.66, 0.55)
    DANGER_DEFAULT = tone(BrandColors.TRADITIONAL_RED, 0.65, 0.65)
    PRIMARY = PRIMARY_DEFAULT
    ACCENT = ACCENT_DEFAULT
    DANGER = DANGER_DEFAULT
    WARM_SURFACE = BrandColors.WARM_WHITE
    EARTH_NEUTRAL = BrandColors.CHARCOAL

    # primary (lightened green for contrast on dark)
    PRIMARY_HOVER = tone(BrandColors.FOREST_GREEN, 0.56, 0.33)
    PRIMARY_PRESSED = tone(BrandColors.FOREST_GREEN, 0.46, 0.30)
    PRIMARY_SUBTLE = tone(BrandColors.FOREST_GREEN, 0.14, 0.24)
    PRIMARY_BORDER = tone(BrandColors.FOREST_GREEN, 0.29, 0.21)

    # accent (gold adjusted for dark)
    ACCENT_HOVER = tone(BrandColors.PREMIUM_GOLD, 0.73, 0.61)
    ACCENT_PRESSED = tone(BrandColors.PREMIUM_GOLD, 0.58, 0.45)
    ACCENT_SUBTLE = tone(BrandColors.PREMIUM_GOLD, 0.13, 0.29)
    ACCENT_TEXT = tone(BrandColors.PREMIUM_GOLD, 0.71, 0.59)

    SUCCESS_DEFAULT = tone(Light.SUCCESS_DEFAULT, 0.54, 0.39)
    SUCCESS_SUBTLE = tone(Light.SUCCESS_DEFAULT, 0.12, 0.27)
    SUCCESS_BORDER = tone(Light.SUCCESS_DEFAULT, 0.33, 0.27)
    SUCCESS = SUCCESS_DEFAULT

    WARNING_DEFAULT = tone(Light.WARNING_DEFAULT, 0.62, 0.68)
    WARNING_SUBTLE = tone(Light.WARNING_DEFAULT, 0.13, 0.38)
    WARNING_BORDER = tone(Light.WARNING_DEFAULT, 0.30, 0.38)
    WARNING = WARNING_DEFAULT

    DANGER_HOVER = tone(BrandColors.TRADITIONAL_RED, 0.72, 0.71)
    DANGER_PRESSED = tone(BrandColors.TRADITIONAL_RED, 0.62, 0.60)
    DANGER_SUBTLE = tone(BrandColors.TRADITIONAL_RED, 0.13, 0.31)
    DANGER_BORDER = tone(BrandColors.TRADITIONAL_RED, 0.32, 0.33)

    INFO_DEFAULT = tone(Light.INFO_DEFAULT, 0.56, 0.43)
    INFO_SUBTLE = tone(Light.INFO_DEFAULT, 0.12, 0.31)
    INFO_BORDER = tone(Light.INFO_DEFAULT, 0.31, 0.32)
    INFO = INFO_DEFAULT

    # surfaces (near-black green → elevated)
    BACKGROUND = BrandScale.CHARCOAL_800
    SURFACE = BrandColors.CHARCOAL
    SURFACE_ELEVATED = BrandScale.CHARCOAL_400
    SURFACE_MUTED = BrandScale.CHARCOAL_700

    # text (warm, gold-hued neutrals)
    TEXT_PRIMARY = tone(BrandColors.PREMIUM_GOLD, 0.90, 0.45)
    TEXT_SECONDARY = tone(BrandColors.PREMIUM_GOLD, 0.72, 0.24)
    TEXT_MUTED = tone(BrandColors.PREMIUM_GOLD, 0.56, 0.14)
    TEXT_INVERSE = tone(BrandColors.FOREST_GREEN, 0.12, 0.20)
    TEXT_DISABLED = tone(BrandColors.PREMIUM_GOLD, 0.38, 0.12)

    BORDER_DEFAULT = tone(BrandColors.FOREST_GREEN, 0.26, 0.12)
    BORDER_SUBTLE = tone(BrandColors.FOREST_GREEN, 0.19, 0.14)
    BORDER_STRONG = tone(BrandColors.FOREST_GREEN, 0.51, 0.08)
    BORDER = BORDER_DEFAULT
    INPUT_BORDER = BORDER_STRONG

    FOCUS_RING = ACCENT_DEFAULT
    SELECTION = tone(BrandColors.FOREST_GREEN, 0.18, 0.25)
    DISABLED_BACKGROUND = tone(BrandColors.FOREST_GREEN, 0.13, 0.15)
    DISABLED_BORDER = tone(BrandColors.FOREST_GREEN, 0.23, 0.11)

    TOOLTIP_BACKGROUND = tone(BrandColors.FOREST_GREEN, 0.05, 0.19)
    TOOLTIP_TEXT = TEXT_PRIMARY


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
        BrandColors.CHARCOAL,
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
        "success": Light.SUCCESS,
        "warning": Light.WARNING,
        "danger": Light.DANGER_DEFAULT,
        "info": Light.INFO,
        "neutral": BrandColors.CHARCOAL,
    }
    FINANCIAL = (BrandColors.FOREST_GREEN, BrandColors.TRADITIONAL_RED,
                 BrandColors.PREMIUM_GOLD)
    INVENTORY = ("#2A6F7A", BrandScale.GREEN_500, BrandColors.PREMIUM_GOLD,
                 BrandColors.TRADITIONAL_RED)
    PRODUCTION = (BrandColors.CHARCOAL, BrandColors.PREMIUM_GOLD,
                  BrandColors.FOREST_GREEN)

    @classmethod
    def for_theme(cls, theme: str):
        """``ChartPalette.for_theme("dark")`` → series legible on dark surfaces."""
        return DarkChartPalette if str(theme).lower() == "dark" else cls


class DarkChartPalette(ChartPalette):
    """Series for the dark theme: every color reaches ≥ 3:1 against the dark
    surface and background (the light palette includes the charcoal surface
    itself and the forest green, both invisible there)."""

    CATEGORICAL = (
        Dark.PRIMARY_DEFAULT,
        Dark.ACCENT_DEFAULT,
        Dark.DANGER_DEFAULT,
        Dark.INFO_DEFAULT,
        Dark.TEXT_SECONDARY,                              # neutral (was charcoal)
        tone(ChartPalette.CATEGORICAL[5], 0.78, 0.45),   # sage green
        tone(ChartPalette.CATEGORICAL[6], 0.45, 0.60),   # dark gold
        tone(ChartPalette.CATEGORICAL[7], 0.68, 0.30),   # muted plum
    )
    SEQUENTIAL = tuple(reversed(ChartPalette.SEQUENTIAL))
    STATUS = {
        "success": Dark.SUCCESS,
        "warning": Dark.WARNING,
        "danger": Dark.DANGER_DEFAULT,
        "info": Dark.INFO,
        "neutral": Dark.TEXT_SECONDARY,
    }
    FINANCIAL = (Dark.PRIMARY_DEFAULT, Dark.DANGER_DEFAULT, Dark.ACCENT_DEFAULT)
    INVENTORY = (Dark.INFO_DEFAULT, Dark.SUCCESS_DEFAULT, Dark.ACCENT_DEFAULT,
                 Dark.DANGER_DEFAULT)
    PRODUCTION = (Dark.TEXT_SECONDARY, Dark.ACCENT_DEFAULT, Dark.PRIMARY_DEFAULT)
