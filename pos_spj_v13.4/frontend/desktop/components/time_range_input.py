"""Canonical time range input for opening/closing or shift ranges."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from frontend.desktop.components.time_input import TimeInput
from frontend.desktop.components.tooltip import Tooltip


class TimeRangeInput(QWidget):
    """Composite HH:mm range input with optional overnight validation."""

    def __init__(
        self,
        parent=None,
        *,
        start_label: str = "Inicio",
        end_label: str = "Fin",
        start_time: str = "08:00",
        end_time: str = "20:00",
        allow_overnight: bool = False,
    ) -> None:
        super().__init__(parent)
        self._allow_overnight = allow_overnight
        self.setObjectName("timeRangeInput")
        self.setProperty("component", "timeRangeInput")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.start_label = QLabel(start_label, self)
        self.start = TimeInput(self)
        self.end_label = QLabel(end_label, self)
        self.end = TimeInput(self)
        for widget in (self.start_label, self.start, self.end_label, self.end):
            layout.addWidget(widget)
        Tooltip.attach(
            self,
            title="Rango horario",
            description="Captura inicio y fin en formato HH:mm.",
        )
        self.set_range(start_time, end_time)

    def set_range(self, start_time: str, end_time: str) -> None:
        self.start.set_time_text(start_time)
        self.end.set_time_text(end_time)
        self.validate_range()

    def range_text(self) -> tuple[str, str]:
        self.validate_range()
        return self.start.time_text(), self.end.time_text()

    def validate_range(self) -> None:
        start = self.start.time_text()
        end = self.end.time_text()
        if start == end:
            raise ValueError("La hora de inicio y fin deben ser diferentes.")
        if not self._allow_overnight and start > end:
            raise ValueError("La hora de fin debe ser posterior a la hora de inicio.")
