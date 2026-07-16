"""Canonical desktop buttons."""

from __future__ import annotations

from PyQt5.QtWidgets import QPushButton

from frontend.desktop.components.tooltip import Tooltip


class StandardButton(QPushButton):
    """Theme-driven button using semantic properties instead of inline styles."""

    def __init__(
        self,
        text: str,
        parent=None,
        *,
        variant: str = "secondary",
        size: str = "md",
        tooltip: str | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("component", "standardButton")
        self.setProperty("variant", variant)
        self.setProperty("size", size)
        self.setAccessibleName(text)
        if tooltip:
            Tooltip.attach(self, title=text, description=tooltip)
