"""Shared shell for the CRM-16 directory pages (clientes/leads/oportunidades/
casos): search + status filter + StandardTable + empty state.

Mirrors ``frontend/desktop/modules/transfers/pages/base_page.py``'s
class-attribute-plus-override shape (``page_id``/``title``/``subtitle`` there,
extended here with a status filter — the search+status-dropdown-+-table
combination ``frontend/desktop/modules/purchasing/pages/
direct_purchase_history_page.py`` already uses is the closest "FilterBar"-
shaped precedent in the repo: §79 names a canonical ``FilterBar`` component
that, like CRM-14's ``ModuleSidebar``/``IconProvider`` and CRM-15's
``ChartDTO``/``ChartBridge``, does not exist under that literal name —
every existing filtered list in this codebase composes it from
``SearchInput`` + ``SearchableComboBox`` instead, so this base class does
the same rather than inventing a new component.

Subclasses declare ``route_id``/``title``/``subtitle``/``icon``/``columns``/
``status_options``/``search_placeholder`` as class attributes and implement
``_fetch(search, status)``/``_row(entity)``.

CRM-17: emits ``entity_selected(row_id)`` on double-click — a directory page
never navigates itself (it doesn't know about routes or other pages, only
its own list), the containing workspace listens and decides what to do.
Only ``customers.directory`` has a real listener as of CRM-17
(``CustomersCrmWorkspace`` opens the Expediente); leads/opportunities/casos
emit into the void harmlessly until their own detail pages exist.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchableComboBox,
    SearchInput,
    SectionCard,
    StandardTable,
    ViewState,
    create_state_widget,
)
from frontend.desktop.themes.tokens import Spacing


class CustomerCrmDirectoryPage(QWidget):
    entity_selected = pyqtSignal(str)

    route_id: str = ""
    title: str = ""
    subtitle: str = ""
    icon: str | None = None
    columns: tuple[ColumnSpec, ...] = ()
    #: (value, label) pairs; the widget always prepends ("", "Todos").
    status_options: tuple[tuple[str, str], ...] = ()
    search_placeholder: str = "Buscar…"
    empty_message: str = "Sin resultados"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._loaded = False
        self.setObjectName("customerCrmDirectoryPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.MD)
        root.addWidget(PageHeader(
            self, title=self.title, subtitle=self.subtitle, icon=self.icon, compact=True))

        self._status = QLabel("", self)
        self._status.setObjectName("customerCrmDirectoryStatus")
        self._status.setProperty("state", "ERROR")
        self._status.setWordWrap(True)
        self._status.hide()
        root.addWidget(self._status)

        card = SectionCard(self, title=self.title)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(Spacing.SM)
        self._search = SearchInput(self, placeholder=self.search_placeholder)
        self._search.setAccessibleName(f"Buscar en {self.title}")
        self._search.search_changed.connect(lambda *_: self.reload())
        filter_row.addWidget(self._search, stretch=1)
        self._status_filter = SearchableComboBox(self, placeholder="Todos los estados")
        self._status_filter.set_options([("", "Todos"), *self.status_options])
        self._status_filter.selection_changed.connect(lambda *_: self.reload())
        filter_row.addWidget(self._status_filter)
        card.body().addLayout(filter_row)

        self._stack = QStackedWidget(self)
        self._table = StandardTable(list(self.columns), self)
        self._table.setAccessibleName(f"Listado de {self.title}")
        self._table.doubleClicked.connect(self._on_row_activated)
        self._empty = create_state_widget(ViewState.EMPTY, self, message=self.empty_message)
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)
        card.body().addWidget(self._stack)
        root.addWidget(card, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            entities = self._fetch(
                search=self._search.text().strip(),
                status=self._status_filter.current_id() or None)
            rows = [self._row(entity) for entity in entities]
            row_ids = [entity.id for entity in entities]
            self._table.load_rows(rows, row_ids=row_ids)
            self._stack.setCurrentWidget(self._table if rows else self._empty)
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setText(f"No fue posible cargar {self.title.lower()}: {exc}")
            self._status.show()

    def _on_row_activated(self, _index) -> None:
        row_id = self._table.selected_row_id()
        if row_id:
            self.entity_selected.emit(row_id)

    def _fetch(self, *, search: str, status: str | None) -> list:
        raise NotImplementedError

    def _row(self, entity) -> list[str]:
        raise NotImplementedError
