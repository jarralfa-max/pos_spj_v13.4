"""GlobalSidebar — SHELL-12.

Composes the design system's existing `SearchInput` and `SideNav` (both
predate this phase) with `SidebarResolver`'s output — this class doesn't
reinvent sidebar rendering, it wires the new declarative/permission layer
(`NavigationItemRegistry`, `SidebarResolver`, badges, search filtering)
onto the widgets that already do it.

`SideNav` addresses rows by index, not by id, so this class keeps a
parallel `route_id` list (`None` for non-interactive group headers) to
translate `SideNav.navigated(int)` into `item_activated(str route_id)`,
and to translate `set_active_route()` back the other way — guarded with
`blockSignals` so a programmatic `set_active_route()` call (made after a
navigation already happened) never re-emits `item_activated` and causes a
navigate-loop.
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.shell.sidebar.sidebar_search import filter_sidebar_items
from frontend.desktop.themes.tokens import Spacing


class GlobalSidebar(QWidget):
    item_activated = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("globalSidebar")

        self._search = SearchInput(self, placeholder="Buscar módulo…", accessible_name="Buscar módulo")
        self._search.search_changed.connect(self._on_search_changed)

        self._nav = SideNav(self)
        self._nav.navigated.connect(self._on_row_navigated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._search)
        layout.addWidget(self._nav, 1)

        self._all_items: tuple[SidebarItemViewModel, ...] = ()
        self._row_route_ids: list[str | None] = []
        self._query = ""

    def set_items(self, items: tuple[SidebarItemViewModel, ...]) -> None:
        self._all_items = items
        self._render(filter_sidebar_items(items, self._query))

    def set_active_route(self, route_id: str | None) -> None:
        if route_id is None or route_id not in self._row_route_ids:
            return
        row = self._row_route_ids.index(route_id)
        self._nav.blockSignals(True)
        try:
            self._nav.select(row)
        finally:
            self._nav.blockSignals(False)

    @property
    def visible_item_count(self) -> int:
        return sum(1 for route_id in self._row_route_ids if route_id is not None)

    @property
    def search_text(self) -> str:
        return self._query

    def _on_search_changed(self, query: str) -> None:
        self._query = query
        self._render(filter_sidebar_items(self._all_items, query))

    def _on_row_navigated(self, row: int) -> None:
        if 0 <= row < len(self._row_route_ids):
            route_id = self._row_route_ids[row]
            if route_id is not None:
                self.item_activated.emit(route_id)

    def _render(self, items: tuple[SidebarItemViewModel, ...]) -> None:
        self._nav.clear()
        self._row_route_ids = []
        current_group: str | None = None
        for item in items:
            if item.group and item.group != current_group:
                self._nav.add_group(item.group)
                self._row_route_ids.append(None)
                current_group = item.group
            elif not item.group:
                current_group = None
            self._nav.add_section(item.label, badge=item.badge_count or 0)
            self._row_route_ids.append(item.route_id)
