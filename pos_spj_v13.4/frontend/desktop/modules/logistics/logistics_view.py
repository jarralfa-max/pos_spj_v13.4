"""Módulo Logística (integración 32cfbf): Contenedores, Embarques y Compra en
origen. «Compra en origen» es la MISMA página de Compras (mismo presentador),
no una segunda implementación."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView, QWidget

from backend.application.logistics.authorization import LogisticsPermissions
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.module_layout import ModuleLayout
from frontend.desktop.components.page_stack import PageStack
from frontend.desktop.components.side_nav import SideNav


@dataclass(frozen=True)
class LogisticsNavEntry:
    page_id: str
    title: str
    icon: str
    permission: str
    tooltip: str


LOGISTICS_NAV: tuple[LogisticsNavEntry, ...] = (
    LogisticsNavEntry("lg_containers", "Contenedores", Icons.PACKAGE,
                      LogisticsPermissions.SHIPMENT_VIEW,
                      "Catálogo de contenedores: alta, estado, historial y QR."),
    LogisticsNavEntry("lg_shipments", "Embarques", Icons.DELIVERY,
                      LogisticsPermissions.SHIPMENT_VIEW,
                      "Viajes y su estado."),
    LogisticsNavEntry("lg_origin", "Compra en origen", Icons.PURCHASES,
                      LogisticsPermissions.SHIPMENT_VIEW,
                      "Recolección en proveedor: cargar, sellar, despachar y recibir."),
)


class LogisticsSidebar(SideNav):
    route_requested = pyqtSignal(str)

    def __init__(self, *, has_permission, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("moduleSidebar")
        self.setProperty("role", "nav")
        self.setAccessibleName("Navegación del módulo de logística")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        for entry in LOGISTICS_NAV:
            if not has_permission(entry.permission):
                continue
            self.add_section(entry.title, entry.icon)
            item = self.item(self.count() - 1)
            item.setData(Qt.UserRole, entry.page_id)
            item.setToolTip(entry.tooltip)
        self.currentItemChanged.connect(
            lambda current, _prev: current is not None
            and self.route_requested.emit(str(current.data(Qt.UserRole))))


class LogisticsView(QWidget):
    def __init__(self, *, has_permission, page_builder, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("logisticsModule")
        self.setAccessibleName("Módulo de logística")
        self._page_builder = page_builder
        self._pages: dict[str, QWidget] = {}
        self.sidebar = LogisticsSidebar(has_permission=has_permission, parent=self)
        self.stack = PageStack(self)
        self.module_layout = ModuleLayout(self, title="Logística", icon=Icons.DELIVERY,
                                          sidebar=self.sidebar, content=self.stack)
        self.sidebar.route_requested.connect(self.show_route)
        if self.sidebar.count():
            self.sidebar.setCurrentRow(0)

    def show_route(self, page_id: str) -> None:
        page = self._pages.get(page_id)
        if page is None:
            page = self._page_builder(page_id)
            self._pages[page_id] = page
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        ensure_loaded = getattr(page, "ensure_loaded", None)
        if callable(ensure_loaded):
            ensure_loaded()
