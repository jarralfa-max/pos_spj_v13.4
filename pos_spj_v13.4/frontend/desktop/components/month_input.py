"""Canonical accounting-period month input."""

from __future__ import annotations

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QDateEdit

from frontend.desktop.components.tooltip import Tooltip


class MonthInput(QDateEdit):
    """Month selector that exposes periods as yyyy-MM."""

    DISPLAY_FORMAT = "yyyy-MM"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("monthInput")
        self.setProperty("component", "monthInput")
        self.setDisplayFormat(self.DISPLAY_FORMAT)
        self.setCalendarPopup(True)
        today = QDate.currentDate()
        self.setDate(QDate(today.year(), today.month(), 1))
        Tooltip.attach(
            self,
            title="Periodo contable",
            description="Selecciona mes y año; se guarda como YYYY-MM.",
        )

    def period_text(self) -> str:
        current = self.date()
        return f"{current.year():04d}-{current.month():02d}"

    def set_period_text(self, value: str) -> None:
        parsed = QDate.fromString(f"{str(value).strip()}-01", "yyyy-MM-dd")
        if not parsed.isValid():
            raise ValueError(f"Periodo inválido: {value!r}. Usa YYYY-MM.")
        self.setDate(parsed)
