"""Canonical table helpers."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem, QWidget

from frontend.desktop.components.buttons import StandardButton
from frontend.desktop.components.status_badge import StatusBadge
from frontend.desktop.components.tooltip import Tooltip


class StandardTable(QTableWidget):
    """Theme-driven table with read-only behavior, automatic tooltips and hidden IDs."""

    def __init__(self, rows: int, columns: int, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.setObjectName("standardTable")
        self.setProperty("component", "standardTable")
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setMinimumHeight(32)

    def configure_headers(self, headers: Sequence[str], *, hidden_headers: Sequence[str] = ()) -> None:
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels([str(header) for header in headers])
        self.hide_columns_by_header(hidden_headers)
        for index, header in enumerate(headers):
            item = self.horizontalHeaderItem(index)
            if item is not None:
                item.setToolTip(str(header))

    def hide_columns_by_header(self, hidden_headers: Sequence[str]) -> None:
        hidden = {str(header) for header in hidden_headers}
        for index in range(self.columnCount()):
            item = self.horizontalHeaderItem(index)
            if item is not None and item.text() in hidden:
                self.setColumnHidden(index, True)

    def set_text(self, row: int, column: int, value: object, *, tooltip: str | None = None) -> None:
        text = "" if value is None else str(value)
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setToolTip(tooltip or text)
        self.setItem(row, column, item)

    def set_status_badge(
        self,
        row: int,
        column: int,
        text: str,
        *,
        status: str = "neutral",
        tooltip: str | None = None,
    ) -> None:
        badge = StatusBadge(text, self, status=status, tooltip=tooltip)
        self.setCellWidget(row, column, badge)

    def set_action_button(
        self,
        row: int,
        column: int,
        text: str,
        callback: Callable[[], None],
        *,
        tooltip: str,
        variant: str = "table_action",
    ) -> None:
        button = StandardButton(text, self, variant=variant, size="sm", tooltip=tooltip)
        button.clicked.connect(lambda _checked=False: callback())
        self.setCellWidget(row, column, button)

    def set_cell_widget_with_tooltip(self, row: int, column: int, widget: QWidget, *, tooltip: str) -> None:
        Tooltip.attach(widget, title=tooltip)
        self.setCellWidget(row, column, widget)
