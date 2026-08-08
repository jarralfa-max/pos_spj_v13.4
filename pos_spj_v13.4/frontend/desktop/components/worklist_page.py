"""WorklistPage — canonical enterprise list-page scaffold (FASE 6 UI/UX).

Header + optional search/status filter + StandardTable with ViewState
empty/error handling + optional master-detail split + optional pagination.
Extracted from Purchasing's ``_ListPageBase`` (the only module that had it)
so Finance/HR can share the same worklist pattern instead of each
reimplementing a thinner one-off.

Two hook styles are supported so a page never needs both:
- override ``_fetch()`` for a paginated/filtered worklist — the default
  ``_load()`` calls it and populates the table for you (Compras' pattern).
- override ``_load()`` directly for a simple page that populates the table
  itself via ``set_table()`` (Finanzas/RRHH's pattern) — the base still
  switches to the empty-state widget afterward if the table ended up empty.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSplitter, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.themes.tokens import Spacing


class WorklistPage(QWidget):
    """Shared scaffold: header + filters + table + view states + pagination."""

    columns: list[ColumnSpec] = []
    title = ""
    subtitle = ""
    icon: str | None = None
    status_filter: list[tuple] = []
    empty_message = "Sin registros"
    searchable: bool = True
    paginated: bool = True
    page_size: int = 50

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._page = 0
        self._total = 0
        self._has_rows: bool | None = None
        self._loaded = False
        self._kpi_container: QWidget | None = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self._layout.setSpacing(Spacing.MD)

        self.header = PageHeader(title=self.title, subtitle=self.subtitle,
                                 icon=self.icon, compact=True)
        self._layout.addWidget(self.header)
        self._build_actions()
        self._notice = QLabel("", self)
        self._notice.setObjectName("procurementInlineNotice")
        self._notice.setWordWrap(True)
        self._notice.hide()
        self._layout.addWidget(self._notice)

        if self.searchable or self.status_filter:
            filters = QHBoxLayout()
            self._search = SearchInput(placeholder="Buscar…")
            self._search.search_changed.connect(self._on_filter)
            self._status = SearchableComboBox(placeholder="Todos los estados")
            if self.status_filter:
                self._status.set_options(self.status_filter)
                self._status.selection_changed.connect(lambda *_: self._on_filter())
            if self.searchable:
                filters.addWidget(self._search, stretch=1)
            if self.status_filter:
                filters.addWidget(self._status)
            self._layout.addLayout(filters)

        if self.columns:
            self._stack = QStackedWidget(self)
            self._table = StandardTable(self.columns, self)
            self.table = self._table  # alias — Finanzas/RRHH pages read `self.table`
            self._table.doubleClicked.connect(lambda *_: self._open_selected())
            self._empty = create_state_widget(ViewState.EMPTY, self, message=self.empty_message)
            self._stack.addWidget(self._table)
            self._stack.addWidget(self._empty)
            self._content = QSplitter(self)
            self._content.setObjectName("procurementMasterDetail")
            self._content.addWidget(self._stack)
            detail = self._create_detail_panel()
            if detail is not None:
                self._content.addWidget(detail)
                self._content.setStretchFactor(0, 3)
                self._content.setStretchFactor(1, 2)
            self._layout.addWidget(self._content, stretch=1)
            self._table.itemSelectionChanged.connect(self._selection_changed)

        self._build_extra()

        row = QHBoxLayout()
        self._build_row_actions(row)
        self._action_buttons = [row.itemAt(index).widget() for index in range(row.count())
                                if row.itemAt(index).widget() is not None]
        if self.columns and self.paginated:
            row.addStretch(1)
            self._prev = create_secondary_button(self, "Anterior")
            self._prev.clicked.connect(self._prev_page)
            self._next = create_secondary_button(self, "Siguiente")
            self._next.clicked.connect(self._next_page)
            self._page_label = QLabel("")
            self._page_label.setProperty("role", "muted")
            row.addWidget(self._page_label)
            row.addWidget(self._prev)
            row.addWidget(self._next)
        if row.count():
            self._layout.addLayout(row)
        if self.columns:
            self._selection_changed()

    # hooks -------------------------------------------------------------------
    def _build_actions(self) -> None:
        """Add page-specific header actions (override)."""

    def _build_extra(self) -> None:
        """Add page-specific widgets below the table (override)."""

    def _build_row_actions(self, row: QHBoxLayout) -> None:
        """Add page-specific buttons to the row below the table (override)."""

    def _fetch(self):
        raise NotImplementedError

    def _load(self) -> None:
        """Default: delegates to ``_fetch()``. Override this directly instead
        for a page that populates the table itself via ``set_table()``."""
        self.set_table(self._fetch())

    def _create_detail_panel(self):
        return None

    def _selection_changed(self):
        selected = bool(self._selected())
        allowed = self._allowed_actions()
        for button in self._action_buttons:
            button.setEnabled(selected and (allowed is None or button.text() in allowed))

    def _allowed_actions(self):
        return None

    def _open_selected(self):
        ...

    # lifecycle ---------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            self._has_rows = None
            self._load()
            if self.columns:
                has_rows = (self._has_rows if self._has_rows is not None
                           else bool(self._table.rowCount()))
                self._stack.setCurrentWidget(self._table if has_rows else self._empty)
                if self.paginated:
                    self._page_label.setText(self._page_text())
            self._loaded = True
        except Exception as exc:
            self._notice.setProperty("state", "ERROR")
            self._notice.setText(f"No fue posible cargar: {exc}")
            self._notice.show()

    def _on_filter(self) -> None:
        self._page = 0
        self.reload()

    def _status_id(self):
        return self._status.current_id() if self.status_filter else None

    def _page_text(self) -> str:
        start = self._page * self.page_size + 1 if self._total else 0
        end = min((self._page + 1) * self.page_size, self._total)
        return f"{start}–{end} de {self._total}"

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.reload()

    def _next_page(self):
        if (self._page + 1) * self.page_size < self._total:
            self._page += 1
            self.reload()

    def _selected(self):
        return self._table.selected_row_id() if self.columns else None

    def selected_id(self):
        return self._selected()

    # helpers -------------------------------------------------------------------
    def set_table(self, model) -> None:
        self._total = getattr(model, "total", len(model.rows))
        self._table.load_rows(model.rows, row_ids=model.row_ids)
        self._has_rows = bool(model.rows)

    def set_kpis(self, kpis) -> None:
        from modulos.ui_components import create_kpi_bar
        if self._kpi_container is not None:
            self._layout.removeWidget(self._kpi_container)
            self._kpi_container.deleteLater()
        items = [{"title": kpi.title, "value": kpi.value, "tone": kpi.variant} for kpi in kpis]
        self._kpi_container = create_kpi_bar(self, items)
        self._layout.insertWidget(1, self._kpi_container)

    def _notify(self, ok, message) -> None:
        self._notice.setProperty("state", "SUCCESS" if ok else "WARNING")
        self._notice.setText(message)
        self._notice.show()
        if ok:
            self.reload()

    def notify(self, ok: bool, message: str) -> None:
        """Alias kept for Finanzas/RRHH pages migrated off QMessageBox — the
        inline notice is the canonical pattern now (never blocks the page)."""
        self._notify(ok, message)
