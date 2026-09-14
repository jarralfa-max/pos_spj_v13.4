"""Canonical button factories (FASE DS-3).

Buttons are never styled inline — they carry a ``variant`` property and pull
their look from the global QSS. Icon-only buttons require a tooltip and an
accessible name. Text is Spanish.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QPushButton

from frontend.desktop.components.icons import IconProvider, Icons, icon_accessible_name
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import ControlHeights, density_metrics
from frontend.desktop.themes.theme_manager import ThemeManager


BUTTON_VARIANTS = ("primary", "secondary", "ghost", "danger", "icon")
_EXISTING_VARIANTS = {"success": "secondary", "warning": "secondary",
                      "outline": "secondary", "table_action": "secondary"}


class _StandardButton(QPushButton):
    def __init__(self, text="", parent=None, *, variant="secondary", tooltip=None):
        super().__init__(text, parent)
        self.setObjectName("standardButton")
        variant = _EXISTING_VARIANTS.get(variant, variant)
        if variant not in BUTTON_VARIANTS:
            raise ValueError(f"Variante de botón no reconocida: {variant}")
        self.setProperty("variant", variant)
        self.setAccessibleName(text or tooltip or "Acción")
        if tooltip:
            apply_tooltip(self, tooltip)
        self._apply_density()
        ThemeManager.instance().density_changed.connect(self._apply_density)

    def _apply_density(self, _density=None):
        metrics = density_metrics()
        if self.property("iconOnly"):
            self.setMinimumSize(metrics.icon_button_size, metrics.icon_button_size)
        else:
            self.setMinimumHeight(metrics.button_height)


class PrimaryButton(_StandardButton):
    def __init__(self, text="", parent=None, *, tooltip=None):
        super().__init__(text, parent, variant="primary", tooltip=tooltip)


class SecondaryButton(_StandardButton):
    def __init__(self, text="", parent=None, *, tooltip=None):
        super().__init__(text, parent, variant="secondary", tooltip=tooltip)


class GhostButton(_StandardButton):
    def __init__(self, text="", parent=None, *, tooltip=None):
        super().__init__(text, parent, variant="ghost", tooltip=tooltip)


class DangerButton(_StandardButton):
    def __init__(self, text="", parent=None, *, tooltip=None):
        super().__init__(text, parent, variant="danger", tooltip=tooltip)


class IconButton(_StandardButton):
    def __init__(self, icon: str, tooltip: str, parent=None, *, variant="icon"):
        if not tooltip:
            raise ValueError("Un botón de solo icono requiere tooltip (accesibilidad).")
        super().__init__("", parent, variant=variant, tooltip=tooltip)
        self.setProperty("iconOnly", True)
        self.setAccessibleName(tooltip or icon_accessible_name(icon))
        IconProvider.bind(self, icon)
        self._apply_density()


def _make(text: str, variant: str, *, parent=None, tooltip: str | None = None,
          min_height: int = ControlHeights.MD) -> QPushButton:
    btn = _StandardButton(text, parent, variant=variant, tooltip=tooltip)
    btn.setMinimumHeight(max(min_height, density_metrics().button_height))
    return btn


def create_primary_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "primary", parent=parent, tooltip=tooltip)


def create_secondary_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    return _make(text, "secondary", parent=parent, tooltip=tooltip)


def create_success_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    btn = _make(text, "secondary", parent=parent, tooltip=tooltip)
    IconProvider.bind(btn, Icons.SUCCESS, state="success")
    return btn


def create_warning_button(parent=None, text: str = "", tooltip: str | None = None) -> QPushButton:
    btn = _make(text, "secondary", parent=parent, tooltip=tooltip)
    IconProvider.bind(btn, Icons.WARNING, state="warning")
    return btn


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


def create_icon_button(parent, icon: str, tooltip: str, *, variant: str = "icon") -> QPushButton:
    """Icon-only button. Tooltip + accessible name are mandatory (never icon-only)."""
    return IconButton(icon, tooltip, parent, variant=variant)
