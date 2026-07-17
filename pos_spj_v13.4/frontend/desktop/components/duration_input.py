"""DurationInput (FASE DS-4) — a duration (amount + unit) → total minutes.

Distinct from TimeInput (a time of day). Never use TimeInput for durations.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QSpinBox, QWidget

from frontend.desktop.themes.tokens import Spacing

_UNIT_MINUTES = {"minutos": 1, "horas": 60, "días": 60 * 24}


class DurationInput(QWidget):
    value_changed = pyqtSignal()

    def __init__(self, parent=None, *, default_unit: str = "minutos",
                 maximum: int = 100000) -> None:
        super().__init__(parent)
        self.setObjectName("durationInput")
        self._amount = QSpinBox(self)
        self._amount.setRange(0, maximum)
        self._unit = QComboBox(self)
        for label in _UNIT_MINUTES:
            self._unit.addItem(label, label)
        idx = self._unit.findData(default_unit)
        if idx >= 0:
            self._unit.setCurrentIndex(idx)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._amount, stretch=1)
        layout.addWidget(self._unit)
        self._amount.valueChanged.connect(lambda _v: self.value_changed.emit())
        self._unit.currentIndexChanged.connect(lambda _i: self.value_changed.emit())

    def total_minutes(self) -> int:
        return self._amount.value() * _UNIT_MINUTES.get(self._unit.currentData(), 1)

    def set_total_minutes(self, minutes: int) -> None:
        minutes = max(0, int(minutes or 0))
        if minutes and minutes % (60 * 24) == 0:
            self._select_unit("días", minutes // (60 * 24))
        elif minutes and minutes % 60 == 0:
            self._select_unit("horas", minutes // 60)
        else:
            self._select_unit("minutos", minutes)

    def _select_unit(self, unit: str, amount: int) -> None:
        idx = self._unit.findData(unit)
        if idx >= 0:
            self._unit.setCurrentIndex(idx)
        self._amount.setValue(amount)
