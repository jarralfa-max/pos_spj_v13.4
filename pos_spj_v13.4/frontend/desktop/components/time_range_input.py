"""TimeRangeInput (FASE DS-4) — start/end 24h range with explicit overnight rule.

Never silently swaps or corrects start/end. ``validate()`` returns a specific
message (or None). Overnight (end < start) is only valid with
``allow_overnight=True``.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from frontend.desktop.components.time_input import TimeInput
from frontend.desktop.themes.tokens import Spacing


class TimeRangeInput(QWidget):
    def __init__(self, parent=None, *, allow_overnight: bool = False,
                 minute_step: int = 5) -> None:
        super().__init__(parent)
        self.setObjectName("timeRangeInput")
        self._allow_overnight = allow_overnight
        self._start = TimeInput(self, minute_step=minute_step)
        self._end = TimeInput(self, minute_step=minute_step)
        self._start.setAccessibleName("Hora de inicio")
        self._end.setAccessibleName("Hora de fin")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._start)
        dash = QLabel("→", self)
        dash.setProperty("role", "muted")
        layout.addWidget(dash)
        layout.addWidget(self._end)

    def set_range(self, start: str, end: str) -> bool:
        ok_start = self._start.set_time_text(start)
        ok_end = self._end.set_time_text(end)
        return ok_start and ok_end

    def start_text(self) -> str:
        return self._start.time_text()

    def end_text(self) -> str:
        return self._end.time_text()

    def allows_overnight(self) -> bool:
        return self._allow_overnight

    def validate(self) -> str | None:
        """Return a specific error message, or None if the range is valid."""
        start, end = self.start_text(), self.end_text()
        if not start:
            return "La hora de apertura es obligatoria."
        if not end:
            return "La hora de cierre es obligatoria."
        if start == end:
            return "La hora de cierre debe ser distinta de la de apertura."
        if end < start and not self._allow_overnight:
            return "La hora de cierre debe ser posterior a la hora de apertura."
        return None
