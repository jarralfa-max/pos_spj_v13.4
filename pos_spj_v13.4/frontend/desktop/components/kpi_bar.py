"""Canonical KPIBar (FASE DS-3) — responsive row/grid of KPICards from DTOs."""

from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QWidget

from frontend.desktop.components.kpi_card import KPICard, KPIDTO
from frontend.desktop.themes.tokens import KpiMetrics, Spacing


class KPIBar(QWidget):
    def __init__(self, parent=None, *, cards: list[KPIDTO] | None = None,
                 min_card_width: int = KpiMetrics.MIN_WIDTH,
                 max_columns: int = KpiMetrics.MAX_COLUMNS,
                 responsive: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("kpiBar")
        self._min_card_width = min_card_width
        self._max_columns = max_columns
        self._responsive = responsive
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(Spacing.MD)
        self._cards: list[KPIDTO] = []
        if cards:
            self.set_cards(cards)

    def set_cards(self, cards: list[KPIDTO]) -> None:
        self._cards = list(cards)
        self._rebuild()

    def _columns(self) -> int:
        if not self._responsive:
            return min(self._max_columns, max(1, len(self._cards)))
        usable = max(self.width(), self._min_card_width)
        fit = max(1, usable // (self._min_card_width + Spacing.MD))
        return max(1, min(self._max_columns, fit, len(self._cards) or 1))

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        cols = self._columns()
        for index, dto in enumerate(self._cards):
            row, col = divmod(index, cols)
            self._grid.addWidget(KPICard(dto, self), row, col)

    def resizeEvent(self, event):  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self._responsive and self._cards:
            self._rebuild()
