"""Canonical table helpers."""

from __future__ import annotations

from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget


class StandardTable(QTableWidget):
    """Theme-driven table with standard read-only behavior."""

    def __init__(self, rows: int, columns: int, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.setProperty("component", "standardTable")
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setMinimumHeight(32)
