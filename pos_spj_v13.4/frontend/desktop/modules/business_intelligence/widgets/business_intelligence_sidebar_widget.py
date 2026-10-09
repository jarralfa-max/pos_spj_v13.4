"""Accessible persistent sidebar for the Business Intelligence workspace.
Mirrors
`frontend/desktop/modules/orders_delivery/widgets/orders_delivery_sidebar_widget.py::OrdersDeliverySidebarWidget`
exactly."""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView

from frontend.desktop.components.side_nav import SideNav

from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (
    visible_entries,
)


class BusinessIntelligenceSidebarWidget(SideNav):
    route_requested = pyqtSignal(str)

    def __init__(self, *, has_permission, badges=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("moduleSidebar")
        self.setProperty("role", "nav")
        self.setAccessibleName("Navegación del módulo de Inteligencia de Negocios")
        self.setAccessibleDescription(
            "Selecciona una sección de Inteligencia de Negocios. Usa las flechas para recorrerla."
        )
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for entry, badge in visible_entries(has_permission, badges):
            title = entry.title if badge is None else f"{entry.title} ({max(0, int(badge))})"
            self.add_section(title, entry.icon)
            item = self.item(self.count() - 1)
            item.setData(Qt.UserRole, entry.page_id)
            item.setToolTip(entry.tooltip)
            item.setData(Qt.AccessibleDescriptionRole, entry.tooltip)
            accessible = entry.title
            if badge is not None:
                accessible = f"{entry.title}, {max(0, int(badge))} pendientes"
            item.setData(Qt.AccessibleTextRole, accessible)
        self.currentItemChanged.connect(self._emit_route)
        if self.count():
            self.setCurrentRow(0)

    def _emit_route(self, current, _previous) -> None:
        if current is not None:
            self.route_requested.emit(str(current.data(Qt.UserRole)))
