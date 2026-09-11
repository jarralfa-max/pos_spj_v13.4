"""Global QSS builder (FASE DS-2).

Generates the application stylesheet from semantic colors + tokens, keyed by
``objectName`` and dynamic ``property`` selectors (variant/size/state). This is
the ONLY place that turns tokens into QSS — pages and widgets must not build
their own stylesheet strings.

Usage:
    qss = build_qss("light")   # or "dark"
    app.setStyleSheet(qss)
"""

from __future__ import annotations

from frontend.desktop.themes.semantic_colors import SemanticColors
from frontend.desktop.themes.tokens import (
    Borders,
    ControlHeights,
    InputMetrics,
    Radii,
    TableMetrics,
    Typography,
    density_metrics,
)


def build_qss(theme: str = "light", *, density="comfortable") -> str:
    c = SemanticColors.for_theme(theme)
    metrics = density_metrics(density)
    parts = [
        _base(c),
        _buttons(c),
        _inputs(c),
        _tables(c),
        _cards(c),
        _kpi(c),
        _page_header(c),
        _sidebar(c),
        _badges(c),
        _tooltip(c),
        _dialogs(c),
        _forms(c),
        _interaction(c, metrics),
    ]
    return "\n\n".join(parts)


def _interaction(c, metrics) -> str:
    """One density and interaction policy also covers native Qt controls."""
    return f'''
QPushButton, QToolButton {{
    background: {c.SURFACE}; color: {c.TEXT_PRIMARY};
    border: 1px solid {c.BORDER_DEFAULT}; border-radius: {Radii.MD}px;
    min-height: {metrics.button_height - 2}px; padding: 0 10px;
}}
QPushButton[variant], QToolButton[variant] {{ min-height: {metrics.button_height - 2}px; }}
QPushButton:hover, QToolButton:hover {{ background: {c.SURFACE_MUTED}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {c.SELECTION}; }}
QPushButton[variant="ghost"], QPushButton[variant="icon"] {{
    background: transparent; border: 1px solid transparent; border-radius: {Radii.MD}px;
}}
QPushButton[variant="ghost"]:hover, QPushButton[variant="icon"]:hover {{ background: {c.PRIMARY_SUBTLE}; }}
QPushButton[variant="ghost"]:pressed, QPushButton[variant="icon"]:pressed {{ background: {c.SELECTION}; }}
QPushButton[iconOnly="true"] {{
    min-width: {metrics.icon_button_size - 2}px;
    min-height: {metrics.icon_button_size - 2}px; padding: 0;
}}
QPushButton:disabled, QToolButton:disabled, QPushButton[variant="ghost"]:disabled,
QPushButton[variant="icon"]:disabled {{
    color: {c.TEXT_DISABLED}; background: {c.DISABLED_BACKGROUND}; border-color: {c.DISABLED_BORDER};
}}
QPushButton:focus, QPushButton[variant]:focus, QToolButton:focus {{
    border: 2px solid {c.FOCUS_RING};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
    min-height: {metrics.input_height - 2 * InputMetrics.PADDING_VERTICAL - 2}px;
}}
QAbstractSpinBox:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    color: {c.TEXT_DISABLED}; background: {c.DISABLED_BACKGROUND}; border-color: {c.DISABLED_BORDER};
}}
QAbstractSpinBox[state="error"], QTextEdit[state="error"], QPlainTextEdit[state="error"] {{
    border: 2px solid {c.DANGER_DEFAULT};
}}
QCheckBox, QRadioButton {{ min-height: {metrics.input_height}px; spacing: 8px; }}
QCheckBox:focus, QRadioButton:focus {{ border: 2px solid {c.FOCUS_RING}; }}
QTabWidget::pane {{ border: 1px solid {c.BORDER_DEFAULT}; background: {c.SURFACE}; }}
QTabBar::tab {{
    min-height: {metrics.tab_height - 2}px; padding: 0 16px;
    color: {c.TEXT_SECONDARY}; background: {c.SURFACE_MUTED}; border: 1px solid {c.BORDER_DEFAULT};
}}
QTabBar::tab:selected {{ color: {c.PRIMARY_DEFAULT}; background: {c.SURFACE}; border-bottom: 3px solid {c.PRIMARY_DEFAULT}; }}
QTabBar::tab:hover {{ background: {c.PRIMARY_SUBTLE}; }}
QTabBar::tab:disabled {{ color: {c.TEXT_DISABLED}; }}
QMenu {{ background: {c.SURFACE_ELEVATED}; border: 1px solid {c.BORDER_DEFAULT}; padding: 4px; }}
QMenu::item {{ min-height: {metrics.sidebar_item_height - 8}px; padding: 4px 20px; }}
QMenu::item:selected {{ background: {c.SELECTION}; color: {c.TEXT_PRIMARY}; }}
QMenu::item:disabled {{ color: {c.TEXT_DISABLED}; }}
QScrollBar:vertical {{ background: {c.SURFACE_MUTED}; width: 16px; margin: 0; }}
QScrollBar:horizontal {{ background: {c.SURFACE_MUTED}; height: 16px; margin: 0; }}
QScrollBar::handle {{ background: {c.BORDER_STRONG}; border-radius: 4px; min-width: 24px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QFrame#topBar, QFrame#globalSidebar, QFrame#moduleSidebar {{ background: {c.SURFACE}; }}
QPushButton[navActive="true"] {{ background: {c.SELECTION}; border-left: 3px solid {c.PRIMARY_DEFAULT}; }}
QLabel[role="notificationBadge"] {{ color: {c.TEXT_INVERSE}; background: {c.DANGER_DEFAULT}; border-radius: 8px; padding: 2px 5px; }}
'''.strip()


def _base(c) -> str:
    return f"""
/* ── base ─────────────────────────────────────────────────────────────── */
QWidget {{
    font-family: {Typography.FONT_FAMILY};
    font-size: {Typography.SIZE_BODY}px;
    color: {c.TEXT_PRIMARY};
    background-color: {c.BACKGROUND};
}}
QWidget:disabled {{ color: {c.TEXT_DISABLED}; }}
QLabel {{ background: transparent; }}
QLabel[role="subtitle"] {{ color: {c.TEXT_SECONDARY}; }}
QLabel[role="muted"] {{ color: {c.TEXT_MUTED}; }}
QLabel#hrEmptyState, QLabel[role="empty"] {{ color: {c.TEXT_MUTED}; }}
""".strip()


def _buttons(c) -> str:
    def variant(name, bg, fg, hover, pressed, border=None):
        border = border or bg
        return f"""
QPushButton[variant="{name}"] {{
    background-color: {bg}; color: {fg};
    border: {Borders.WIDTH_THIN}px solid {border};
    border-radius: {Radii.MD}px;
    min-height: {ControlHeights.MD}px;
    padding: 0 {InputMetrics.PADDING_HORIZONTAL + 4}px;
    font-weight: {Typography.WEIGHT_SEMIBOLD};
}}
QPushButton[variant="{name}"]:hover {{ background-color: {hover}; border-color: {hover}; }}
QPushButton[variant="{name}"]:pressed {{ background-color: {pressed}; border-color: {pressed}; }}
QPushButton[variant="{name}"]:disabled {{
    background-color: {c.DISABLED_BACKGROUND}; color: {c.TEXT_DISABLED};
    border-color: {c.DISABLED_BORDER};
}}"""

    outline = f"""
QPushButton[variant="outline"] {{
    background-color: transparent; color: {c.PRIMARY_DEFAULT};
    border: {Borders.WIDTH_THIN}px solid {c.PRIMARY_BORDER};
    border-radius: {Radii.MD}px; min-height: {ControlHeights.MD}px;
    padding: 0 {InputMetrics.PADDING_HORIZONTAL + 4}px;
    font-weight: {Typography.WEIGHT_MEDIUM};
}}
QPushButton[variant="outline"]:hover {{ background-color: {c.PRIMARY_SUBTLE}; }}
QPushButton[variant="ghost"] {{
    background-color: transparent; color: {c.PRIMARY_DEFAULT};
    border: none; min-height: {ControlHeights.MD}px;
    padding: 0 {InputMetrics.PADDING_HORIZONTAL}px;
}}
QPushButton[variant="ghost"]:hover {{ background-color: {c.PRIMARY_SUBTLE}; }}
QPushButton:focus {{ outline: none; border: {Borders.WIDTH_FOCUS}px solid {c.FOCUS_RING}; }}"""

    return "\n".join([
        "/* ── buttons ──────────────────────────────────────────────────────── */",
        variant("primary", c.PRIMARY_DEFAULT, c.TEXT_INVERSE, c.PRIMARY_HOVER, c.PRIMARY_PRESSED),
        variant("secondary", c.SURFACE, c.TEXT_PRIMARY, c.SURFACE_MUTED, c.BORDER_DEFAULT, c.BORDER_DEFAULT),
        variant("success", c.SUCCESS_DEFAULT, c.TEXT_INVERSE, c.SUCCESS_DEFAULT, c.SUCCESS_DEFAULT),
        variant("warning", c.WARNING_DEFAULT, c.TEXT_INVERSE, c.WARNING_DEFAULT, c.WARNING_DEFAULT),
        variant("danger", c.DANGER_DEFAULT, c.TEXT_INVERSE, c.DANGER_HOVER, c.DANGER_PRESSED),
        variant("accent", c.ACCENT_DEFAULT, c.TEXT_PRIMARY, c.ACCENT_HOVER, c.ACCENT_PRESSED),
        outline,
    ])


def _inputs(c) -> str:
    return f"""
/* ── inputs ───────────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
QDateTimeEdit, QPlainTextEdit, QTextEdit {{
    background-color: {c.SURFACE};
    color: {c.TEXT_PRIMARY};
    border: {Borders.WIDTH_THIN}px solid {c.BORDER_DEFAULT};
    border-radius: {Radii.SM}px;
    min-height: {ControlHeights.MD - 8}px;
    padding: {InputMetrics.PADDING_VERTICAL}px {InputMetrics.PADDING_HORIZONTAL}px;
    selection-background-color: {c.SELECTION};
    selection-color: {c.TEXT_PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QPlainTextEdit:focus,
QTextEdit:focus {{ border: {Borders.WIDTH_FOCUS}px solid {c.FOCUS_RING}; }}
QLineEdit:disabled, QComboBox:disabled {{
    background-color: {c.DISABLED_BACKGROUND}; color: {c.TEXT_DISABLED};
    border-color: {c.DISABLED_BORDER};
}}
QLineEdit[state="error"], QComboBox[state="error"] {{ border-color: {c.DANGER_DEFAULT}; }}
QLineEdit[state="warning"] {{ border-color: {c.WARNING_DEFAULT}; }}
QLineEdit[readOnly="true"] {{ background-color: {c.SURFACE_MUTED}; color: {c.TEXT_SECONDARY}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
""".strip()


def _tables(c) -> str:
    return f"""
/* ── tables ───────────────────────────────────────────────────────────── */
QTableWidget#standardTable, QTableView#standardTable {{
    background-color: {c.SURFACE};
    alternate-background-color: {c.SURFACE_MUTED};
    gridline-color: {c.BORDER_SUBTLE};
    border: {Borders.WIDTH_THIN}px solid {c.BORDER_DEFAULT};
    border-radius: {Radii.MD}px;
    selection-background-color: {c.SELECTION};
    selection-color: {c.TEXT_PRIMARY};
}}
QTableWidget#standardTable::item {{ padding: 4px 8px; min-height: {TableMetrics.ROW_HEIGHT}px; }}
QHeaderView::section {{
    background-color: {c.SURFACE_MUTED};
    color: {c.TEXT_SECONDARY};
    padding: 6px 8px;
    border: none;
    border-bottom: {Borders.WIDTH_THIN}px solid {c.BORDER_DEFAULT};
    min-height: {TableMetrics.HEADER_HEIGHT - 12}px;
    font-weight: {Typography.WEIGHT_SEMIBOLD};
}}
""".strip()


def _cards(c) -> str:
    def card(sel, bg, border):
        return f"""{sel} {{
    background-color: {bg};
    border: {Borders.WIDTH_THIN}px solid {border};
    border-radius: {Radii.LG}px;
}}"""
    return "\n".join([
        "/* ── cards ────────────────────────────────────────────────────────── */",
        card("QFrame#standardCard", c.SURFACE, c.BORDER_DEFAULT),
        card('QFrame[cardVariant="section"]', c.SURFACE, c.BORDER_DEFAULT),
        card('QFrame[cardVariant="summary"]', c.SURFACE_ELEVATED, c.BORDER_DEFAULT),
        card('QFrame[cardVariant="info"]', c.INFO_SUBTLE, c.INFO_BORDER),
        card('QFrame[cardVariant="alert"]', c.WARNING_SUBTLE, c.WARNING_BORDER),
        card('QFrame[cardVariant="danger"]', c.DANGER_SUBTLE, c.DANGER_BORDER),
        card('QFrame[cardVariant="chart"]', c.SURFACE, c.BORDER_DEFAULT),
    ])


def _kpi(c) -> str:
    def accent(variant, color):
        return f'QFrame#kpiCard[variant="{variant}"] {{ border-left: 4px solid {color}; }}'
    variants = "\n".join([
        accent("primary", c.PRIMARY_DEFAULT),
        accent("success", c.SUCCESS_DEFAULT),
        accent("warning", c.WARNING_DEFAULT),
        accent("danger", c.DANGER_DEFAULT),
        accent("info", c.INFO_DEFAULT),
        accent("accent", c.ACCENT_DEFAULT),
        accent("neutral", c.BORDER_STRONG),
    ])
    return f"""
/* ── kpi ──────────────────────────────────────────────────────────────── */
QFrame#kpiCard {{
    background-color: {c.SURFACE};
    border: {Borders.WIDTH_THIN}px solid {c.BORDER_DEFAULT};
    border-radius: {Radii.LG}px;
}}
QLabel#kpiTitle {{ color: {c.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}px;
    font-weight: {Typography.WEIGHT_SEMIBOLD}; }}
QLabel#kpiValue {{ color: {c.TEXT_PRIMARY}; font-size: {Typography.SIZE_KPI_VALUE}px;
    font-weight: {Typography.WEIGHT_BOLD}; }}
QLabel#kpiSubtitle {{ color: {c.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}px; }}
{variants}
""".strip()


def _page_header(c) -> str:
    return f"""
/* ── page header ──────────────────────────────────────────────────────── */
QFrame#pageHeader {{ background: transparent; border-bottom: {Borders.WIDTH_THIN}px solid {c.BORDER_SUBTLE}; }}
QLabel#pageHeaderTitle {{ color: {c.TEXT_PRIMARY}; font-size: {Typography.SIZE_TITLE}px;
    font-weight: {Typography.WEIGHT_BOLD}; }}
QLabel#pageHeaderSubtitle {{ color: {c.TEXT_SECONDARY}; font-size: {Typography.SIZE_BODY}px; }}
""".strip()


def _sidebar(c) -> str:
    return f"""
/* ── sidebar / nav ────────────────────────────────────────────────────── */
QListWidget#sideNav, QListWidget#financeNav, QListWidget#hrNav, QListWidget[role="nav"] {{
    background-color: {c.SURFACE_MUTED};
    border: none;
    border-right: {Borders.WIDTH_THIN}px solid {c.BORDER_DEFAULT};
    outline: none;
}}
QListWidget#sideNav::item, QListWidget#financeNav::item, QListWidget#hrNav::item,
QListWidget[role="nav"]::item {{
    padding: 8px 12px; color: {c.TEXT_SECONDARY}; border-radius: {Radii.SM}px;
}}
QListWidget#sideNav::item:selected, QListWidget#financeNav::item:selected, QListWidget#hrNav::item:selected,
QListWidget[role="nav"]::item:selected {{
    background-color: {c.PRIMARY_SUBTLE}; color: {c.PRIMARY_DEFAULT};
    border-left: 3px solid {c.PRIMARY_DEFAULT};
}}
""".strip()


def _badges(c) -> str:
    def badge(variant, bg, fg, border):
        return (f'QLabel#statusBadge[variant="{variant}"] {{ background-color: {bg};'
                f' color: {fg}; border: {Borders.WIDTH_THIN}px solid {border};'
                f' border-radius: {Radii.PILL}px; padding: 2px 10px; }}')
    return "\n".join([
        "/* ── status badges ────────────────────────────────────────────────── */",
        badge("neutral", c.SURFACE_MUTED, c.TEXT_SECONDARY, c.BORDER_DEFAULT),
        badge("info", c.INFO_SUBTLE, c.INFO_DEFAULT, c.INFO_BORDER),
        badge("success", c.SUCCESS_SUBTLE, c.SUCCESS_DEFAULT, c.SUCCESS_BORDER),
        badge("warning", c.WARNING_SUBTLE, c.WARNING_DEFAULT, c.WARNING_BORDER),
        badge("danger", c.DANGER_SUBTLE, c.DANGER_DEFAULT, c.DANGER_BORDER),
        badge("accent", c.ACCENT_SUBTLE, c.ACCENT_TEXT, c.ACCENT_DEFAULT),
    ])


def _tooltip(c) -> str:
    return f"""
/* ── tooltip ──────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {c.TOOLTIP_BACKGROUND};
    color: {c.TOOLTIP_TEXT};
    border: {Borders.WIDTH_THIN}px solid {c.BORDER_STRONG};
    border-radius: {Radii.SM}px;
    padding: 6px 8px;
}}
""".strip()


def _dialogs(c) -> str:
    return f"""
/* ── dialogs ──────────────────────────────────────────────────────────── */
QDialog#standardDialog {{ background-color: {c.BACKGROUND}; }}
QDialog#standardDialog QLabel[role="dialogTitle"] {{
    font-size: {Typography.SIZE_SUBTITLE}px; font-weight: {Typography.WEIGHT_SEMIBOLD};
    color: {c.TEXT_PRIMARY};
}}
""".strip()


def _forms(c) -> str:
    return f"""
/* ── forms / specialized inputs ───────────────────────────────────────── */
QLabel#formFieldLabel {{ color: {c.TEXT_SECONDARY}; font-weight: {Typography.WEIGHT_MEDIUM}; }}
QLabel#formFieldHelper {{ color: {c.TEXT_MUTED}; font-size: {Typography.SIZE_CAPTION}px; }}
QLabel#formFieldError, QLabel[state="error"] {{
    color: {c.DANGER_DEFAULT}; font-size: {Typography.SIZE_CAPTION}px;
}}
QLineEdit#filePathField[readOnly="true"] {{
    background-color: {c.SURFACE_MUTED}; color: {c.TEXT_SECONDARY};
}}
QListWidget#entitySearchResults {{
    background-color: {c.SURFACE}; border: {Borders.WIDTH_THIN}px solid {c.BORDER_DEFAULT};
    border-radius: {Radii.SM}px;
}}
QListWidget#entitySearchResults::item {{ padding: 6px 8px; }}
QListWidget#entitySearchResults::item:selected {{
    background-color: {c.SELECTION}; color: {c.TEXT_PRIMARY};
}}
""".strip()
