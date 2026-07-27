"""Canonical responsive KPI bar."""

from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QWidget

from frontend.desktop.components.kpi_card import KPIDTO, KPICard
from frontend.desktop.themes import DesktopSpacing


class KPIBar(QWidget):
    def __init__(self, cards: tuple[KPIDTO, ...], parent=None, *, max_columns: int = 4) -> None:
        super().__init__(parent)
        self.setProperty("component", "kpiBar")
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(DesktopSpacing.MD)
        self._cards: dict[str, KPICard] = {}
        for index, dto in enumerate(cards):
            card = KPICard(dto, self)
            self._cards[dto.key] = card
            self._layout.addWidget(card, index // max_columns, index % max_columns)

    def update_value(self, key: str, value: str) -> None:
        if key in self._cards:
            self._cards[key].set_value(value)
