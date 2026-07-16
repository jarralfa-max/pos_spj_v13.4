"""StandardTable — canonical table policy for every new module.

Policy (SPJ_UI_UX_ARCHITECTURE_SKILL §7.3): 32px rows/headers, word wrap on
descriptive columns, automatic tooltips, hidden internal ids, stretch for
descriptive columns, resize-to-contents for numeric/date columns, no inline
colors (theme QSS owns the look).
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


@dataclass(frozen=True)
class ColumnSpec:
    """title: visible header (Spanish). kind: 'text' | 'numeric' | 'date' | 'status'."""

    title: str
    kind: str = "text"


class StandardTable(QTableWidget):
    def __init__(self, columns: list[ColumnSpec], parent=None) -> None:
        super().__init__(parent)
        self._columns = columns
        self.setObjectName("standardTable")
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([col.title for col in columns])
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        header = self.horizontalHeader()
        header.setMinimumHeight(32)
        for index, col in enumerate(columns):
            if col.kind == "text":
                header.setSectionResizeMode(index, QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeToContents)

    def load_rows(self, rows: list[list[str]], *, row_ids: list[str] | None = None) -> None:
        """Fill the table. ``row_ids`` are stored as hidden Qt.UserRole data."""
        self.setRowCount(0)
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                if self._columns[col_index].kind == "numeric":
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if row_ids is not None and col_index == 0:
                    item.setData(Qt.UserRole, row_ids[row_index])
                self.setItem(row_index, col_index, item)

    def selected_row_id(self) -> str | None:
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return item.data(Qt.UserRole) if item is not None else None
