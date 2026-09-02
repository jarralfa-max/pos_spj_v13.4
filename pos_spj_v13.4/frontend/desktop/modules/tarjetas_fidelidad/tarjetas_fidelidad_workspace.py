"""LOY-25 workspace shell for the Tarjetas Fidelidad desktop UI. Mirrors
``frontend/desktop/modules/fidelidad/fidelidad_workspace.py``'s shape
exactly, scaled to what LOY-25 built: real pages for Resumen/Tarjetas/
Plantillas; every other declared route falls back to the canonical
``ViewState.EMPTY`` placeholder."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.tarjetas_fidelidad.pages.cards_page import CardsPage
from frontend.desktop.modules.tarjetas_fidelidad.pages.overview_page import (
    TarjetasFidelidadOverviewPage,
)
from frontend.desktop.modules.tarjetas_fidelidad.pages.templates_page import TemplatesPage
from frontend.desktop.modules.tarjetas_fidelidad.tarjetas_fidelidad_routes import (
    grouped_routes,
    visible_routes,
)
from frontend.desktop.themes.tokens import ResponsiveBreakpoints, Spacing


class TarjetasFidelidadWorkspace(QWidget):
    """Responsive module shell for Tarjetas Fidelidad."""

    def __init__(self, presenter, parent=None, *,
                 page_factories: dict[str, Callable] | None = None):
        super().__init__(parent)
        self._presenter = presenter
        self._page_factories = page_factories or {}
        self._route_index_by_id: dict[str, int] = {}
        self.setObjectName("tarjetasFidelidadWorkspace")
        self.setAccessibleName("Modulo de Tarjetas Fidelidad")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL,
                                Spacing.PAGE_MARGIN_HORIZONTAL, Spacing.PAGE_MARGIN_VERTICAL)
        root.setSpacing(Spacing.MD)

        self._header = PageHeader(
            self, title="Tarjetas Fidelidad",
            subtitle="Tarjetas físicas y digitales, plantillas, lotes e impresión.",
            icon=Icons.LOYALTY_CARDS, compact=self._initial_compact())
        root.addWidget(self._header)

        shell = QHBoxLayout()
        shell.setSpacing(Spacing.LG)
        root.addLayout(shell, stretch=1)

        self._nav = SideNav(self)
        self._nav.setProperty("role", "nav")
        self._nav.setAccessibleName("Navegacion de Tarjetas Fidelidad")
        self._nav.navigated.connect(self._on_navigated)
        shell.addWidget(self._nav)

        self._stack = QStackedWidget(self)
        self._stack.setObjectName("tarjetasFidelidadStack")
        self._stack.setAccessibleName("Paginas del modulo de Tarjetas Fidelidad")
        shell.addWidget(self._stack, stretch=1)

        self._build_routes()
        self.select_route("tarjetas.overview")
        self._ensure_active_page_loaded()

    def _initial_compact(self) -> bool:
        width = self.window().width() if self.window() else 0
        return 0 < width < ResponsiveBreakpoints.COMPACT

    def _build_routes(self) -> None:
        self._route_index_by_id.clear()
        row = 0
        page_index = 0
        routes_by_group = self._visible_grouped_routes()
        if not routes_by_group:
            self._nav.add_group("Tarjetas Fidelidad")
            self._stack.addWidget(create_state_widget(
                ViewState.NO_PERMISSION, self,
                message="No tienes permiso para consultar el modulo de Tarjetas Fidelidad."))
            return
        for group, routes in routes_by_group:
            self._nav.add_group(group)
            row += 1
            for route in routes:
                self._nav.add_section(route.label)
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
        return grouped_routes(visible_routes(self._presenter.capabilities()))

    def _wrap_page(self, route_id: str, label: str, tooltip: str) -> QWidget:
        page = QFrame(self)
        page.setObjectName("tarjetasFidelidadPageHost")
        page.setAccessibleName(label)
        page.setAccessibleDescription(tooltip)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        content = self._create_page(route_id, label, tooltip)
        scroll = QScrollArea(page)
        scroll.setObjectName("tarjetasFidelidadScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _create_page(self, route_id: str, label: str, tooltip: str) -> QWidget:
        if route_id in self._page_factories:
            return self._page_factories[route_id](self)
        if route_id == "tarjetas.overview":
            return TarjetasFidelidadOverviewPage(self._presenter, self)
        if route_id == "tarjetas.cards":
            return CardsPage(self._presenter, self)
        if route_id == "tarjetas.templates":
            return TemplatesPage(self._presenter, self)

        placeholder = create_state_widget(
            ViewState.EMPTY, self,
            message=f"{label}: seccion en construccion (proxima fase).")
        apply_tooltip(placeholder, tooltip, help_id=f"tarjetas_fidelidad.{route_id}")
        return placeholder

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
        elif "tarjetas.overview" in self._route_index_by_id:
            self.select_route("tarjetas.overview")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.width() < ResponsiveBreakpoints.COMPACT
        self._nav.setMaximumWidth(180 if compact else 240)
        self._nav.setMinimumWidth(160 if compact else 180)
