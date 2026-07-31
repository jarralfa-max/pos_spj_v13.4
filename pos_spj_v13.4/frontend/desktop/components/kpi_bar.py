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
        self._widgets: list[KPICard] = []
        if cards:
            self.set_cards(cards)

    def set_cards(self, cards: list[KPIDTO]) -> None:
        cards = list(cards)
        # §8.4: si el conjunto de KPIs (por `key`, mismo orden) no cambió, actualiza
        # las tarjetas EN SITIO en vez de destruir/recrear (evita ciclos de
        # deleteLater en cada refresco cuando sólo cambian valores).
        if ([c.key for c in cards] == [c.key for c in self._cards]
                and len(self._widgets) == len(cards)):
            self._cards = cards
            for widget, dto in zip(self._widgets, cards):
                widget.update(dto)
            return
        self._cards = cards
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
        self._widgets = []
        cols = self._columns()
        for index, dto in enumerate(self._cards):
            row, col = divmod(index, cols)
            card = KPICard(dto, self)
            self._grid.addWidget(card, row, col)
            self._widgets.append(card)

    def resizeEvent(self, event):  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        if self._responsive and self._cards:
            self._rebuild()
