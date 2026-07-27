"""Canonical HH:mm time input for desktop forms."""

from __future__ import annotations

from datetime import time

from PyQt5.QtCore import QTime
from PyQt5.QtWidgets import QTimeEdit

from frontend.desktop.components.tooltip import Tooltip


class TimeInput(QTimeEdit):
    """Theme-aware time input that persists and exposes values as HH:mm."""

    DISPLAY_FORMAT = "HH:mm"

    def __init__(self, parent=None, *, minute_step: int = 1, nullable: bool = False) -> None:
        super().__init__(parent)
        if minute_step <= 0 or 60 % minute_step != 0:
            raise ValueError("minute_step debe ser un divisor positivo de 60.")
        self._minute_step = minute_step
        self._nullable = nullable
        self.setObjectName("timeInput")
        self.setProperty("component", "timeInput")
        self.setDisplayFormat(self.DISPLAY_FORMAT)
        self.setKeyboardTracking(False)
        Tooltip.attach(
            self,
            title="Hora",
            description="Hora en formato de 24 horas, por ejemplo 08:00.",
        )

    def set_time_text(self, value: str) -> None:
        parsed = QTime.fromString(str(value).strip(), self.DISPLAY_FORMAT)
        if not parsed.isValid() or parsed.toString(self.DISPLAY_FORMAT) != str(value).strip():
            raise ValueError(f"Hora inválida: {value!r}. Usa HH:mm.")
        self.setTime(parsed)

    def time_text(self) -> str:
        return self.time().toString(self.DISPLAY_FORMAT)

    def python_time(self) -> time:
        current = self.time()
        return time(current.hour(), current.minute())
