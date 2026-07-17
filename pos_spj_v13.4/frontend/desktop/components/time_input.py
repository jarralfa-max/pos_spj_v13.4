"""TimeInput (FASE DS-4) — canonical 24h HH:mm time field.

Built on ``QTimeEdit`` (never a free-text QLineEdit). Persists/returns ``HH:mm``
strings for recurring local times without a date. Rejects malformed input by
construction (the spinner only yields valid times).
"""

from __future__ import annotations

from PyQt5.QtCore import QTime, pyqtSignal
from PyQt5.QtWidgets import QTimeEdit

from frontend.desktop.components.tooltip import apply_tooltip

_DISPLAY_FORMAT = "HH:mm"


class TimeInput(QTimeEdit):
    time_text_changed = pyqtSignal(str)

    def __init__(self, parent=None, *, minute_step: int = 5,
                 nullable: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("timeInput")
        self.setDisplayFormat(_DISPLAY_FORMAT)
        self.setWrapping(True)
        self._minute_step = max(1, minute_step)
        self._nullable = nullable
        self.setAccessibleName("Hora")
        apply_tooltip(self, "Hora en formato de 24 horas, por ejemplo 08:00.")
        self.timeChanged.connect(lambda _t: self.time_text_changed.emit(self.time_text()))

    def set_time_text(self, value: str) -> bool:
        """Set from ``HH:mm``. Returns False (and leaves value) if malformed."""
        parsed = QTime.fromString(str(value).strip(), _DISPLAY_FORMAT)
        if not parsed.isValid():
            return False
        self.setTime(parsed)
        return True

    def time_text(self) -> str:
        """Return the current value as ``HH:mm`` (24h)."""
        return self.time().toString(_DISPLAY_FORMAT)

    def step_minutes(self) -> int:
        return self._minute_step

    def stepBy(self, steps):  # noqa: N802 (Qt override) — honor minute_step
        if self.currentSection() == QTimeEdit.MinuteSection:
            self.setTime(self.time().addSecs(steps * self._minute_step * 60))
        else:
            super().stepBy(steps)
