"""Canonical responsive Configuración page shell using only SPJ Design
System components — mirrors
`frontend/desktop/modules/transfers/pages/base_page.py`. Unlike Transfers
(one uniform 5-column layout everywhere), each Configuración section has
its own column set, so the table is rebuilt from the query service's
`ConfigColumnDTO` list on every `reload()` rather than declared once in
`__init__` — the view state (LOADING while the table is rebuilt is
skipped, this is a synchronous local SQLite read) goes straight to
READY/EMPTY via `create_state_widget`.
"""
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec, PageHeader, SearchInput, SectionCard, StandardTable, ViewState, create_state_widget,
)
from frontend.desktop.themes.tokens import Spacing


class ConfiguracionWorkspacePage(QWidget):
    page_id = ""
    title = "Configuración"
    subtitle = ""
    action_text = ""

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("configuracionPage")
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(self, title=self.title, subtitle=self.subtitle))
        self.search = SearchInput(self, placeholder=f"Buscar en {self.title.lower()}…")
        self.search.setAccessibleName(f"Buscar en {self.title}")
        self.search.search_changed.connect(self.reload)
        root.addWidget(self.search)
        self.card = SectionCard(self, title=self.title)
        self.table: StandardTable | None = None
        self.state_widget = create_state_widget(ViewState.LOADING, self.card)
        self.card.add(self.state_widget)
        root.addWidget(self.card, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload("")

    def reload(self, search: str = "") -> None:
        model = self._presenter.load_page(self.page_id, search)
        self._rebuild_table(model.columns)
        rows = [list(row.cells) for row in model.rows]
        self.table.load_rows(rows, row_ids=[row.entity_id for row in model.rows])
        self._show_state(ViewState.EMPTY if not rows else ViewState.READY, model.empty_message)
        self._loaded = True

    # helpers -----------------------------------------------------------------
    def _rebuild_table(self, columns) -> None:
        if self.table is not None:
            self.table.setParent(None)
        self.table = StandardTable([ColumnSpec(c.title, c.kind) for c in columns], self.card)
        self.table.setAccessibleName(f"Listado de {self.title}")
        self.card.add(self.table)

    def _show_state(self, state: str, message: str) -> None:
        if self.state_widget is not None:
            self.state_widget.setParent(None)
        if state == ViewState.EMPTY:
            self.state_widget = create_state_widget(ViewState.EMPTY, self.card, message=message)
            self.card.add(self.state_widget)
        else:
            self.state_widget = None
        self.table.setVisible(state != ViewState.EMPTY)
