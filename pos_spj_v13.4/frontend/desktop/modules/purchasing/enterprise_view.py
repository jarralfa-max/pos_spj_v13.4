"""EnterprisePurchasingView — tabbed container for the enterprise procurement UI
(dashboard, direct purchase, requisitions, orders, invoices) inside Compras.

Receives a fully wired EnterprisePurchasingPresenter and a DirectPurchaseView;
never touches the database. Each tab loads lazily on first activation.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from frontend.desktop.modules.purchasing.pages.enterprise_pages import (
    InvoicesPage,
    OrdersPage,
    RequisitionsPage,
)
from frontend.desktop.modules.purchasing.pages.procurement_dashboard_page import (
    ProcurementDashboardPage,
)


class EnterprisePurchasingView(QWidget):
    def __init__(self, presenter, parent=None, *, direct_purchase_view=None) -> None:
        super().__init__(parent)
        self.setObjectName("enterprisePurchasingModule")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("purchasingTabs")
        layout.addWidget(self._tabs)

        self._dashboard = ProcurementDashboardPage(presenter, self)
        self._requisitions = RequisitionsPage(presenter, self)
        self._orders = OrdersPage(presenter, self)
        self._invoices = InvoicesPage(presenter, self)

        self._tabs.addTab(self._dashboard, "Panel")
        if direct_purchase_view is not None:
            self._tabs.addTab(direct_purchase_view, "Compra directa")
            self._direct = direct_purchase_view
        else:
            self._direct = None
        self._tabs.addTab(self._requisitions, "Solicitudes")
        self._tabs.addTab(self._orders, "Órdenes")
        self._tabs.addTab(self._invoices, "Facturas")

        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._on_tab_changed(0)

    def _on_tab_changed(self, _index: int) -> None:
        widget = self._tabs.currentWidget()
        loader = getattr(widget, "ensure_loaded", None)
        if callable(loader):
            loader()

    def ensure_loaded(self) -> None:
        self._dashboard.ensure_loaded()

    def reload(self) -> None:
        widget = self._tabs.currentWidget()
        reloader = getattr(widget, "reload", None)
        if callable(reloader):
            reloader()
