"""Workspace shell for the Fidelidad desktop UI (LOY-25, LOY-29).

Mirrors ``frontend/desktop/modules/customers_crm/customers_crm_workspace.py``'s
shape. LOY-29: every route has a real page — declarative record pages
(``records/catalog.py``, ``records/cards_catalog.py``) or a purpose-built one
(resumen, alertas, perfil de miembro, recompensas, diseñador, QR, ajustes).
There is no "en construcción" fallback any more: an unknown route is a bug and
raises.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.module_layout import ModuleLayout
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.fidelidad.fidelidad_routes import (
    GROUP_ICONS,
    grouped_routes,
    visible_routes,
)
from frontend.desktop.modules.fidelidad.pages.alerts_page import FidelidadAlertsPage
from frontend.desktop.modules.fidelidad.pages.member_profile_page import MemberProfilePage
from frontend.desktop.modules.fidelidad.pages.overview_page import FidelidadOverviewPage
from frontend.desktop.modules.fidelidad.pages.rewards_page import RewardsPage
from frontend.desktop.modules.fidelidad.records import catalog
from frontend.desktop.modules.fidelidad.records.record_page import LoyaltyRecordPage
from frontend.desktop.modules.fidelidad.records.specs import RecordPageSpec, TabbedSpec
from frontend.desktop.modules.fidelidad.records.tabbed_page import LoyaltyTabbedRecordPage
from frontend.desktop.themes.tokens import Spacing


class FidelidadWorkspace(QWidget):
    """Responsive module shell for Fidelidad."""

    def __init__(self, presenter, parent=None, *,
                 page_factories: dict[str, Callable] | None = None):
        super().__init__(parent)
        self._presenter = presenter
        self._page_factories = page_factories or {}
        self._route_index_by_id: dict[str, int] = {}
        self.setObjectName("fidelidadWorkspace")
        self.setAccessibleName("Modulo de Fidelidad")

        self._nav = SideNav(self)
        self._nav.setProperty("role", "nav")
        self._nav.setAccessibleName("Navegacion de Fidelidad")
        self._nav.navigated.connect(self._on_navigated)
        self._stack = QStackedWidget(self)
        self._stack.setObjectName("fidelidadStack")
        self._stack.setAccessibleName("Paginas del modulo de Fidelidad")
        self.module_layout = ModuleLayout(
            self, title="Fidelidad",
            subtitle="Programas, puntos, recompensas, cupones, vales y sorteos.",
            icon=Icons.LOYALTY, sidebar=self._nav, content=self._stack,
        )
        self._header = self.module_layout.header

        self._build_routes()
        self.select_route("fidelidad.overview")
        self._ensure_active_page_loaded()

    def _build_routes(self) -> None:
        self._route_index_by_id.clear()
        row = 0
        page_index = 0
        routes_by_group = self._visible_grouped_routes()
        if not routes_by_group:
            self._nav.add_group("Fidelidad", icon=Icons.LOYALTY)
            self._stack.addWidget(create_state_widget(
                ViewState.NO_PERMISSION, self,
                message="No tienes permiso para consultar el modulo de Fidelidad."))
            return
        for group, routes in routes_by_group:
            self._nav.add_group(group, icon=GROUP_ICONS[group])
            row += 1
            for route in routes:
                self._nav.add_section(route.label, icon=route.icon)
                item = self._nav.item(row)
                if item is not None:
                    item.setToolTip(route.tooltip)
                    item.setData(Qt.UserRole, route.route_id)
                    item.setData(Qt.AccessibleDescriptionRole, route.tooltip)
                self._route_index_by_id[route.route_id] = page_index
                self._stack.addWidget(self._wrap_page(route.route_id, route.label, route.tooltip))
                row += 1
                page_index += 1

    def _visible_grouped_routes(self) -> list[tuple[str, list]]:
        return grouped_routes(visible_routes(self._presenter.capabilities(),
                                             can=getattr(self._presenter, "can", None)))

    def _wrap_page(self, route_id: str, label: str, tooltip: str) -> QWidget:
        page = QFrame(self)
        page.setObjectName("fidelidadPageHost")
        page.setAccessibleName(label)
        page.setAccessibleDescription(tooltip)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        content = self._create_page(route_id, label, tooltip)
        scroll = QScrollArea(page)
        scroll.setObjectName("fidelidadScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _create_page(self, route_id: str, label: str, tooltip: str) -> QWidget:
        if route_id in self._page_factories:
            return self._page_factories[route_id](self)
        if route_id == "fidelidad.overview":
            return FidelidadOverviewPage(self._presenter, self, navigate=self.select_route)
        if route_id == "fidelidad.alerts":
            return FidelidadAlertsPage(self._presenter, self, navigate=self.select_route)
        if route_id == "fidelidad.settings":
            from frontend.desktop.modules.fidelidad.pages.program_settings_page import (
                ProgramSettingsPage,
            )
            return ProgramSettingsPage(self._presenter, self)
        if route_id == "loyalty.member_profile":
            return MemberProfilePage(self._presenter, self)
        if route_id == "loyalty.rewards":
            return LoyaltyTabbedRecordPage(
                self._presenter, TabbedSpec(
                    key="rewards", title="Recompensas",
                    subtitle="Catálogo, canje por cliente y entregas.",
                    tabs=(("Catálogo", catalog.REWARD_CATALOG),
                          ("Canjes", catalog.REWARD_REDEMPTIONS))),
                self, extra_tabs=(("Canjear", RewardsPage(self._presenter, self), 1),))
        if route_id.startswith("cards."):
            from frontend.desktop.modules.fidelidad.cards.card_pages import create_card_page
            return create_card_page(route_id, self._presenter, self)
        spec = catalog.FIDELIDAD_RECORD_ROUTES[route_id]
        if isinstance(spec, RecordPageSpec):
            return LoyaltyRecordPage(self._presenter, spec, self)
        return LoyaltyTabbedRecordPage(self._presenter, spec, self)

    def _on_navigated(self, nav_row: int) -> None:
        item = self._nav.item(nav_row)
        route_id = item.data(Qt.UserRole) if item is not None else None
        if route_id in self._route_index_by_id:
            self._stack.setCurrentIndex(self._route_index_by_id[route_id])
            self._ensure_active_page_loaded()

    def select_route(self, route_id: str) -> None:
        target_index = self._route_index_by_id.get(route_id)
        if target_index is None:
            return
        for row in range(self._nav.count()):
            item = self._nav.item(row)
            if item is not None and item.data(Qt.UserRole) == route_id:
                self._nav.setCurrentRow(row)
                break
        self._stack.setCurrentIndex(target_index)
        self._ensure_active_page_loaded()

    def _ensure_active_page_loaded(self) -> None:
        host = self._stack.currentWidget()
        if host is None:
            return
        scroll = host.findChild(QScrollArea)
        page = scroll.widget() if scroll is not None else None
        if page is not None and hasattr(page, "ensure_loaded"):
            page.ensure_loaded()

    def refresh_permissions(self) -> None:
        current_id = None
        current_index = self._stack.currentIndex()
        for route_id, index in self._route_index_by_id.items():
            if index == current_index:
                current_id = route_id
                break
        while self._stack.count():
            widget = self._stack.widget(0)
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._nav.clear()
        self._build_routes()
        if current_id in self._route_index_by_id:
            self.select_route(current_id)
        elif "fidelidad.overview" in self._route_index_by_id:
            self.select_route("fidelidad.overview")
