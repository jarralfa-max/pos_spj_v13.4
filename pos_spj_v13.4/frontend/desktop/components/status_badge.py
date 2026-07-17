"""StatusBadge (DS-3) — themed via the global QSS ``#statusBadge[variant]``.

Color is never the sole indicator: the badge always carries text. No inline
colors — the look comes from the theme layer.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

_VALID_VARIANTS = ("neutral", "info", "success", "warning", "danger", "accent")


class StatusBadge(QLabel):
    def __init__(self, text: str = "Pendiente", parent=None, *,
                 status: str = "neutral") -> None:
        super().__init__(text, parent)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        variant = status if status in _VALID_VARIANTS else "neutral"
        self.setProperty("variant", variant)
        self.setAccessibleName(f"{self.text()} ({variant})")
        # re-polish so the property-based QSS re-applies
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
