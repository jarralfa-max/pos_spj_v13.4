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

from PyQt5.QtCore import QSettings, Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.branding import BrandLabel
from frontend.desktop.components.buttons import create_icon_button
from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.shell.sidebar.sidebar_search import filter_sidebar_items
from frontend.desktop.themes.tokens import Spacing


class GlobalSidebar(QWidget):
    item_activated = pyqtSignal(str)
    collapsed_changed = pyqtSignal(bool)

    def __init__(self, parent=None, *, settings=None, settings_key: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("globalSidebar")
        self.setAccessibleName("Menú principal")
        self._settings = settings if settings is not None else (QSettings("JUANIS", "SPJ") if settings_key else None)
        self._settings_key = f"navigation/{settings_key}" if settings_key else ""
        self._active_route = str(self._settings.value(f"{self._settings_key}/active_route", "")) if self._settings else ""
        self._collapsed = False
        self._brand = BrandLabel(self)
        self._toggle = create_icon_button(self, Icons.CHEVRON_LEFT, "Contraer menú principal")
        self._toggle.clicked.connect(lambda: self.set_collapsed(not self._collapsed))

        self._search = SearchInput(self, placeholder="Buscar módulo…", accessible_name="Buscar módulo")
        self._search.search_changed.connect(self._on_search_changed)

        self._nav = SideNav(self, toggle_visible=False, group_flyouts=False)
        self._nav.setAccessibleName("Módulos de la aplicación")
        self._nav.setMinimumWidth(0)
        self._nav.setMaximumWidth(16777215)
        self._nav.navigated.connect(self._on_row_navigated)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        layout.setSpacing(Spacing.SM)
        layout.addWidget(self._brand)
        layout.addWidget(self._toggle, 0, Qt.AlignRight)
        layout.addWidget(self._search)
        layout.addWidget(self._nav, 1)

        self._all_items: tuple[SidebarItemViewModel, ...] = ()
        self._row_route_ids: list[str | None] = []
        self._query = ""
        collapsed = self._settings.value(f"{self._settings_key}/collapsed", False, type=bool) if self._settings else False
        self.set_collapsed(collapsed)

    def set_items(self, items: tuple[SidebarItemViewModel, ...]) -> None:
        self._all_items = items
        if self._active_route not in {item.route_id for item in items}:
            self._active_route = next((item.route_id for item in items if item.is_active), "")
        self._render(filter_sidebar_items(items, self._query))

    def set_active_route(self, route_id: str | None) -> None:
        if route_id is None or route_id not in {item.route_id for item in self._all_items}:
            return
        self._active_route = route_id
        if self._settings is not None:
            self._settings.setValue(f"{self._settings_key}/active_route", route_id)
        if route_id not in self._row_route_ids:
            return
        row = self._row_route_ids.index(route_id)
        self._nav.blockSignals(True)
        try:
            self._nav.select(row)
        finally:
            self._nav.blockSignals(False)

    @property
    def active_route(self) -> str:
        return self._active_route

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        width = 64 if self._collapsed else 240
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)
        self._brand.set_isotype(self._collapsed)
        self._search.setVisible(not self._collapsed)
        self._nav.set_collapsed(self._collapsed)
        # The containing rail controls width; its inner list fills the content.
        self._nav.setMinimumWidth(0)
        self._nav.setMaximumWidth(16777215)
        self.layout().setContentsMargins(4 if self._collapsed else Spacing.SM, Spacing.SM,
                                        4 if self._collapsed else Spacing.SM, Spacing.SM)
        icon = Icons.CHEVRON_RIGHT if self._collapsed else Icons.CHEVRON_LEFT
        IconProvider.bind(self._toggle, icon)
        label = "Expandir menú principal" if self._collapsed else "Contraer menú principal"
        self._toggle.setToolTip(label)
        self._toggle.setAccessibleName(label)
        if self._settings is not None:
            self._settings.setValue(f"{self._settings_key}/collapsed", self._collapsed)
        self.collapsed_changed.emit(self._collapsed)

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
        self._nav.blockSignals(True)
        try:
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
                self._nav.add_section(item.label, icon=item.icon, badge=item.badge_count or 0)
                self._row_route_ids.append(item.route_id)
            if self._active_route in self._row_route_ids:
                self._nav.select(self._row_route_ids.index(self._active_route))
        finally:
            self._nav.blockSignals(False)


AppSidebar = GlobalSidebar
