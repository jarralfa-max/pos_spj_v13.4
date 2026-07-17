"""Canonical button factories (FASE DS-3).

Buttons are never styled inline — they carry a ``variant`` property and pull
their look from the global QSS. Icon-only buttons require a tooltip and an
accessible name. Text is Spanish.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QPushButton

from frontend.desktop.components.icons import icon_accessible_name
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import ControlHeights


def _make(text: str, variant: str, *, parent=None, tooltip: str | None = None,
          min_height: int = ControlHeights.MD) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setObjectName("standardButton")
    btn.setProperty("variant", variant)
    btn.setMinimumHeight(min_height)
    if text:
        btn.setAccessibleName(text)
    if tooltip:
        apply_tooltip(btn, tooltip)
    return btn


def create_primary_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "primary", parent=parent, tooltip=tooltip)


def create_secondary_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "secondary", parent=parent, tooltip=tooltip)


def create_success_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "success", parent=parent, tooltip=tooltip)


def create_warning_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "warning", parent=parent, tooltip=tooltip)


def create_danger_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "danger", parent=parent, tooltip=tooltip)


def create_outline_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "outline", parent=parent, tooltip=tooltip)


def create_ghost_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "ghost", parent=parent, tooltip=tooltip)


def create_table_action_button(parent, text: str, tooltip: str,
                               variant: str = "outline") -> QPushButton:
    return _make(text, variant, parent=parent, tooltip=tooltip,
                 min_height=ControlHeights.TABLE_ACTION)


def create_icon_button(parent, icon: str, tooltip: str, *, variant: str = "ghost") -> QPushButton:
    """Icon-only button. Tooltip + accessible name are mandatory (never icon-only)."""
    if not tooltip:
        raise ValueError("Un botón de solo icono requiere tooltip (accesibilidad).")
    btn = _make("", variant, parent=parent, tooltip=tooltip,
                min_height=ControlHeights.ICON_BUTTON)
    btn.setProperty("icon", icon)
    btn.setAccessibleName(icon_accessible_name(icon))
    btn.setFixedWidth(ControlHeights.ICON_BUTTON)
    return btn
