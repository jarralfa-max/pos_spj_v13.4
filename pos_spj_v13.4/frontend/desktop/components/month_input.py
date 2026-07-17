"""MonthInput (FASE DS-4) — a monthly period ``yyyy-MM`` (not a generic date)."""

from __future__ import annotations

from PyQt5.QtCore import QDate, pyqtSignal
from PyQt5.QtWidgets import QDateEdit

_FORMAT = "yyyy-MM"


class MonthInput(QDateEdit):
    month_changed = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("monthInput")
        self.setDisplayFormat(_FORMAT)
        self.setCalendarPopup(True)
        self.setDate(QDate.currentDate())
        self.dateChanged.connect(lambda _d: self.month_changed.emit(self.month_text()))

    def month_text(self) -> str:
        """Return ``yyyy-MM`` (day is irrelevant for a monthly period)."""
        d = self.date()
        return f"{d.year():04d}-{d.month():02d}"

    def set_month_text(self, value: str) -> bool:
        try:
            year, month = str(value).split("-")
            qd = QDate(int(year), int(month), 1)
        except (ValueError, TypeError):
            return False
        if not qd.isValid():
            return False
        self.setDate(qd)
        return True
