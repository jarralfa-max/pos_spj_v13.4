# modulos/whatsapp/panels/_panel_styles.py
"""Theme-aware styling utilities for WhatsApp panels."""
from modulos.design_tokens import Colors, Spacing, Typography, Borders


def _is_dark() -> bool:
    try:
        from ui.themes.theme_engine import get_current_theme
        t = get_current_theme().lower()
        return "oscur" in t or "dark" in t
    except Exception:
        return True


def group_box_style() -> str:
    """Returns empty — global QSS owns QGroupBox background/border per theme."""
    return ""


def info_banner_style(variant: str = "neutral") -> str:
    """Transparent-background info strip — inherits the panel's theme background."""
    dark = _is_dark()
    _borders = {
        "neutral": Colors.NEUTRAL.SLATE_700 if dark else Colors.NEUTRAL.SLATE_200,
        "info":    Colors.INFO.BASE,
        "warning": Colors.WARNING.BASE,
        "success": Colors.SUCCESS.BASE,
        "danger":  Colors.DANGER.BASE,
    }
    _texts = {
        "neutral": Colors.NEUTRAL.SLATE_400 if dark else Colors.NEUTRAL.SLATE_600,
        "info":    Colors.INFO.BASE,
        "warning": Colors.WARNING.BASE,
        "success": Colors.SUCCESS.BASE,
        "danger":  Colors.DANGER.BASE,
    }
    return (
        f"background: transparent;"
        f"color: {_texts.get(variant, _texts['neutral'])};"
        f"border: 1px solid {_borders.get(variant, _borders['neutral'])};"
        f"border-radius: {Borders.RADIUS_LG}px;"
        f"padding: {Spacing.SM}px {Spacing.MD}px;"
        f"font-size: {Typography.SIZE_SM};"
    )


def input_style() -> str:
    """QLineEdit style — no background so global QSS sets the theme-correct color."""
    dark = _is_dark()
    border = Colors.NEUTRAL.SLATE_600 if dark else Colors.NEUTRAL.SLATE_300
    return (
        f"QLineEdit {{"
        f"  border: 1px solid {border};"
        f"  border-radius: {Borders.RADIUS_LG}px;"
        f"  padding: {Spacing.XS}px {Spacing.SM}px;"
        f"  font-size: {Typography.SIZE_MD};"
        f"}}"
        f"QLineEdit:focus {{"
        f"  border-color: {Colors.PRIMARY.BASE};"
        f"}}"
    )
