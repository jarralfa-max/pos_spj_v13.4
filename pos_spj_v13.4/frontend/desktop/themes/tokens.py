"""Design tokens (FASE DS-2) — the single source for non-color visual constants.

Spacing, typography, sizing, radii, elevation, control heights, icon sizes and
per-component metrics. Modules and components must import these instead of
repeating raw pixel numbers. Colors live in ``semantic_colors.py``.
"""

from __future__ import annotations


class Spacing:
    XXS = 2
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32
    XXXL = 48
    SECTION_GAP = 24
    PAGE_MARGIN_HORIZONTAL = 20
    PAGE_MARGIN_VERTICAL = 16


class Typography:
    FONT_FAMILY = "Segoe UI, Inter, 'Helvetica Neue', Arial, sans-serif"
    SIZE_CAPTION = 11
    SIZE_BODY_SM = 12
    SIZE_BODY = 13
    SIZE_BODY_LG = 14
    SIZE_SUBTITLE = 15
    SIZE_TITLE = 18
    SIZE_TITLE_LG = 22
    SIZE_DISPLAY = 28
    SIZE_KPI_VALUE = 24
    WEIGHT_REGULAR = 400
    WEIGHT_MEDIUM = 500
    WEIGHT_SEMIBOLD = 600
    WEIGHT_BOLD = 700
    LINE_HEIGHT = 1.4


class Radii:
    NONE = 0
    SM = 4
    MD = 6
    LG = 10
    XL = 14
    PILL = 999


class Borders:
    WIDTH_THIN = 1
    WIDTH_MEDIUM = 2
    WIDTH_FOCUS = 2


class Elevation:
    NONE = 0
    CARD = 1
    RAISED = 2
    OVERLAY = 3
    MODAL = 4


class ControlHeights:
    SM = 28
    MD = 32
    LG = 36
    TABLE_ACTION = 26
    ICON_BUTTON = 32
    DIALOG_BUTTON = 32


class InputMetrics:
    PADDING_HORIZONTAL = 10
    PADDING_VERTICAL = 6
    MIN_WIDTH = 160


class IconSizes:
    XS = 14
    SM = 16
    MD = 20
    LG = 24
    XL = 32


class TableMetrics:
    ROW_HEIGHT = 32
    HEADER_HEIGHT = 32
    ACTION_COLUMN_WIDTH = 120


class DialogMetrics:
    WIDTH_SM = 420
    WIDTH_MD = 560
    WIDTH_LG = 760
    PADDING = 16


class KpiMetrics:
    MIN_HEIGHT = 96
    MAX_HEIGHT = 112
    MIN_WIDTH = 190
    ICON_SIZE = 36
    ACCENT_SIZE = 4
    MAX_COLUMNS = 5


class CardMetrics:
    PADDING_SM = 12
    PADDING_MD = 16
    PADDING_LG = 20
    RADIUS = Radii.LG
    BORDER_WIDTH = Borders.WIDTH_THIN


class ChartMetrics:
    HEIGHT_SM = 220
    HEIGHT_MD = 320
    HEIGHT_LG = 420
    HEIGHT_XL = 520


class TooltipMetrics:
    MAX_WIDTH = 320
    DELAY_MS = 400


class SidebarMetrics:
    WIDTH = 240
    ITEM_HEIGHT = 40


class ResponsiveBreakpoints:
    """Minimum widths (px). The reference validation targets are 1366, 1440, 1920."""

    COMPACT = 1366
    STANDARD = 1440
    WIDE = 1920


class AnimationDurations:
    FAST_MS = 120
    BASE_MS = 200
    SLOW_MS = 320
