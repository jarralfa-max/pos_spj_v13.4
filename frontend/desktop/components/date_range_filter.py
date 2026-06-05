"""Standard date range filter component."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QDate, pyqtSignal
from PyQt5.QtWidgets import QDateEdit, QHBoxLayout, QLabel, QWidget


@dataclass(frozen=True)
class DateRange:
    start: QDate
    end: QDate


class DateRangeFilter(QWidget):
    range_changed = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        today = QDate.currentDate()
        self._start = QDateEdit(today, self)
        self._end = QDateEdit(today, self)
        self._start.setCalendarPopup(True)
        self._end.setCalendarPopup(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Desde", self))
        layout.addWidget(self._start)
        layout.addWidget(QLabel("Hasta", self))
        layout.addWidget(self._end)

        self._start.dateChanged.connect(self._emit_range)
        self._end.dateChanged.connect(self._emit_range)

    def value(self) -> DateRange:
        return DateRange(start=self._start.date(), end=self._end.date())

    def set_range(self, date_range: DateRange) -> None:
        self._start.setDate(date_range.start)
        self._end.setDate(date_range.end)

    def _emit_range(self) -> None:
        self.range_changed.emit(self.value())
