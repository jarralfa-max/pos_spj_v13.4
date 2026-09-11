"""StandardTable — canonical table policy for every new module.

Policy (SPJ_UI_UX_ARCHITECTURE_SKILL §7.3): 32px rows/headers, word wrap on
descriptive columns, automatic tooltips, hidden internal ids, stretch for
descriptive columns, resize-to-contents for numeric/date columns, no inline
colors (theme QSS owns the look).
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QSettings, Qt, QTimer
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import TableMetrics, density_metrics


@dataclass(frozen=True)
class ColumnSpec:
    """title: visible header (Spanish). kind: 'text' | 'numeric' | 'date' | 'status'."""

    title: str
    kind: str = "text"
    key: str = ""
    min_width: int = 80
    preferred_width: int = 160
    stretch: bool | None = None
    priority: int = 0
    hide_below: int | None = None
    alignment: int | None = None

    def __post_init__(self):
        if self.min_width <= 0 or self.preferred_width < self.min_width:
            raise ValueError("Column widths must be positive and preferred_width >= min_width")


class _TableItem(QTableWidgetItem):
    def __lt__(self, other):
        own = self.data(Qt.UserRole + 1)
        theirs = other.data(Qt.UserRole + 1)
        if own is not None and theirs is not None:
            return own < theirs
        return super().__lt__(other)


class StandardTable(QTableWidget):
    def __init__(self, columns: list[ColumnSpec], parent=None, *, settings=None,
                 settings_key: str = "", density=None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._density = density
        self._settings = settings if settings is not None else QSettings("JUANIS", "SPJ")
        self._settings_key = settings_key
        self._saved_widths = {}
        self._visibility = {}
        self._resizing = False
        self._filter_text = ""
        self._loading = False
        self.setObjectName("standardTable")
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([col.title for col in columns])
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setProperty("overflowPolicy", "auto")
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setMinimumSectionSize(1)
        for index, col in enumerate(columns):
            header.setSectionResizeMode(index, QHeaderView.Interactive)
        self._state_label = QLabel("Sin registros", self.viewport())
        self._state_label.setObjectName("tableState")
        self._state_label.setAlignment(Qt.AlignCenter)
        self._state_label.setWordWrap(True)
        self._state_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.sectionResized.connect(self._section_resized)
        ThemeManager.instance().density_changed.connect(self._density_changed)
        self._density_changed()
        self.restore_column_layout()

    def _density_changed(self, _density=None):
        metrics = density_metrics(self._density)
        self.verticalHeader().setMinimumSectionSize(metrics.table_row_height)
        self.verticalHeader().setDefaultSectionSize(metrics.table_row_height)
        self.horizontalHeader().setMinimumHeight(metrics.table_row_height)

    def _column_key(self, index):
        return self._columns[index].key or self._columns[index].title

    def restore_column_layout(self):
        if self._settings_key:
            value = self._settings.value(f"tables/{self._settings_key}/columns", {})
            if isinstance(value, dict):
                for index, col in enumerate(self._columns):
                    state = value.get(self._column_key(index), {})
                    if isinstance(state, dict):
                        width = state.get("width")
                        if isinstance(width, (int, float)):
                            self._saved_widths[index] = max(col.min_width, int(width))
                        visible = state.get("visible")
                        if isinstance(visible, bool):
                            self._visibility[index] = visible
        self._layout_columns()

    def save_column_layout(self):
        if self._settings_key:
            value = {self._column_key(index): {"width": self._saved_widths.get(index, col.preferred_width),
                     **({"visible": self._visibility[index]} if index in self._visibility else {})}
                     for index, col in enumerate(self._columns)}
            self._settings.setValue(f"tables/{self._settings_key}/columns", value)

    def set_column_visible(self, index: int, visible: bool):
        if not 0 <= index < len(self._columns):
            raise IndexError(index)
        self._visibility[index] = bool(visible)
        self._layout_columns()
        self.save_column_layout()

    def _section_resized(self, index, _old, width):
        if self._resizing or self.isColumnHidden(index):
            return
        self._saved_widths[index] = max(self._columns[index].min_width, width)
        self._layout_columns()
        self.save_column_layout()

    def _layout_columns(self):
        if self._resizing:
            return
        self._resizing = True
        try:
            available = max(0, self.viewport().width())
            visible = []
            for index, col in enumerate(self._columns):
                show = self._visibility.get(index, col.hide_below is None or available >= col.hide_below)
                if show:
                    visible.append(index)
            # Priority zero is essential; only explicitly optional columns collapse.
            for index in sorted(visible, key=lambda i: self._columns[i].priority, reverse=True):
                if sum(self._columns[i].min_width for i in visible) <= available:
                    break
                if self._columns[index].priority > 0 and index not in self._visibility:
                    visible.remove(index)
            widths = {i: self._saved_widths.get(i, self._columns[i].preferred_width) for i in visible}
            stretch = [i for i in visible if i not in self._saved_widths and
                       (self._columns[i].stretch if self._columns[i].stretch is not None else self._columns[i].kind == "text")]
            extra = max(0, available - sum(widths.values()))
            for position, index in enumerate(stretch):
                widths[index] += extra // len(stretch) + (position < extra % len(stretch))
            for index in range(len(self._columns)):
                self.setColumnHidden(index, index not in visible)
                if index in widths:
                    self.setColumnWidth(index, widths[index])
        finally:
            self._resizing = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_state_label"):
            self._layout_columns()
            self._state_label.setGeometry(self.viewport().rect())

    def set_loading(self, loading: bool = True):
        self._loading = bool(loading)
        self.setEnabled(not loading)
        self._update_state()

    def set_filter(self, text: str):
        self._filter_text = text.casefold().strip()
        for row in range(self.rowCount()):
            self.setRowHidden(row, bool(self._filter_text) and not any(
                self.item(row, col) is not None and self._filter_text in self.item(row, col).text().casefold()
                for col in range(self.columnCount())))
        self._update_state()

    def _update_state(self):
        empty = not any(not self.isRowHidden(row) for row in range(self.rowCount()))
        message = "Cargando…" if self._loading else ("Sin resultados" if self._filter_text else "Sin registros")
        self._state_label.setText(message)
        self._state_label.setAccessibleName(message)
        self._state_label.setGeometry(self.viewport().rect())
        self._state_label.setVisible(self._loading or empty)

    def load_rows(self, rows: list[list[str]], *, row_ids: list[str] | None = None) -> None:
        """Fill the table. ``row_ids`` are stored as hidden Qt.UserRole data."""
        if row_ids is not None and len(row_ids) != len(rows):
            raise ValueError("row_ids must contain one identity per row")
        if any(len(row) != len(self._columns) for row in rows):
            raise ValueError("Every row must match the column specification")
        sorting = self.isSortingEnabled()
        self.setSortingEnabled(False)
        self.setUpdatesEnabled(False)
        try:
            self.setRowCount(0)
            self.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                for col_index, value in enumerate(row):
                    self._set_value(row_index, col_index, value, row_ids)
        finally:
            self.setSortingEnabled(sorting)
            self.setUpdatesEnabled(True)
        self._loading = False
        self.setEnabled(True)
        self.set_filter(self._filter_text)

    def _set_value(self, row_index, col_index, value, row_ids):
                text = "" if value is None else str(value)
                item = _TableItem(text)
                item.setToolTip(text)
                col = self._columns[col_index]
                if col.alignment is not None:
                    item.setTextAlignment(int(col.alignment))
                elif col.kind == "numeric":
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if col.kind == "numeric":
                    from decimal import Decimal, InvalidOperation
                    try:
                        item.setData(Qt.UserRole + 1, Decimal(text.replace(",", "").replace("$", "").strip()))
                    except InvalidOperation:
                        pass
                if row_ids is not None:
                    item.setData(Qt.UserRole, row_ids[row_index])
                self.setItem(row_index, col_index, item)

    def selected_row_id(self) -> str | None:
        row = self.currentRow()
        if row < 0:
            return None
        current = self.currentItem()
        if current is not None:
            row_id = current.data(Qt.UserRole)
            if row_id:
                return row_id
        item = self.item(row, 0)
        return item.data(Qt.UserRole) if item is not None else None
