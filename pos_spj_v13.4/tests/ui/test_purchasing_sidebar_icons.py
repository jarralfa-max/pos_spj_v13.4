"""Purchasing sidebar uses route artwork without changing capability filtering."""
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QEvent, pyqtSignal
from PyQt5.QtWidgets import QWidget

from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.modules.purchasing import purchasing_module_shell as module
from frontend.desktop.modules.purchasing.navigation import PurchasingRoutes as Routes
from frontend.desktop.themes.theme_manager import ThemeManager


class PageBody(QWidget):
    route_requested = pyqtSignal(str)
    direct_purchase_requested = pyqtSignal(dict)

    def __init__(self, presenter=None, parent=None, **kwargs):
        super().__init__(parent)
        self.loads = 0

    def ensure_loaded(self):
        self.loads += 1


class Presenter:
    def __init__(self, granted=True):
        self.grants = SimpleNamespace(**{name: granted for name in (
            "module_view", "requisition_view", "quotation_view", "order_view",
            "direct_create", "direct_view", "origin_view", "receipt_view", "invoice_view")})

    def capabilities(self):
        return self.grants

    def session_summary(self):
        return {"branch": "Sucursal de prueba", "warehouse_selected": False}

    def warehouse_options(self):
        return []

    def analytics_kpis(self):
        return {}

    def navigation_badges(self, kpis):
        return {"orders": 3}


@pytest.fixture
def shell(qt_font_resources, monkeypatch):
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light")
    for name in ("ProcurementDashboardPage", "RequisitionsPage", "QuotationsPage", "OrdersPage",
                 "LogisticsRelatedPage", "PurchaseHistoryPage", "InvoicesPage"):
        monkeypatch.setattr(module, name, PageBody)
    presenter = Presenter()
    view = module.PurchasingModuleShell(presenter, direct_purchase_views={
        "create": PageBody(), "history": PageBody()})
    yield view, presenter, manager
    view.deleteLater()
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_purchasing_routes_render_distinct_semantic_icons(shell, qt_font_resources, theme):
    view, presenter, manager = shell
    expected = {Routes.DASHBOARD: Icons.DASHBOARD, Routes.REQUISITIONS: Icons.REQUEST,
                Routes.QUOTATIONS: Icons.PRICE, Routes.ORDERS: Icons.ORDERS,
                Routes.DIRECT_PURCHASE_CREATE: Icons.ADD, Routes.DIRECT_PURCHASE_HISTORY: Icons.CLOCK,
                Routes.ORIGIN_LOADING: Icons.PICKING, Routes.RECEIPTS: Icons.RECEIVING,
                Routes.INVOICES: Icons.DOCUMENT}
    assert list(view._route_to_row) == list(expected)
    manager.set_theme(theme, app=qt_font_resources)
    view.reload()
    for route, icon in expected.items():
        row = view._route_to_row[route]
        item = view.sidebar.item(row)
        assert item.data(view.sidebar._ICON_ROLE) == icon
        assert item.icon().pixmap(24, 24).toImage() == IconProvider.icon(icon).pixmap(24, 24).toImage()
        view.navigate_to(route)
        assert view.content.currentIndex() == view._route_to_page[route]
        assert view.content.currentWidget().loads > 0
    assert view.sidebar.item(view._route_to_row[Routes.ORDERS]).data(view.sidebar._BADGE_ROLE) == 3
    view.sidebar.set_collapsed(True)
    for row in range(view.sidebar.count()):
        item = view.sidebar.item(row)
        assert item.data(view.sidebar._ICON_ROLE) != Icons.HOME
        if item.data(view.sidebar._GROUP_ROLE):
            menu = view.sidebar.group_menu(row)
            menu.actions()[0].trigger()
            assert view.content.currentIndex() == view._row_to_page[row + 1]
            menu.deleteLater()


def test_purchasing_permission_refresh_preserves_available_route_icons(shell):
    view, presenter, manager = shell
    presenter.grants.order_view = False
    view.refresh_permissions()
    assert Routes.ORDERS not in view._route_to_row
    assert view.sidebar.item(view._route_to_row[Routes.REQUISITIONS]).data(view.sidebar._ICON_ROLE) == Icons.REQUEST
    for name in vars(presenter.grants):
        setattr(presenter.grants, name, False)
    view.refresh_permissions()
    assert list(view._route_to_row) == ["no_access"]
    assert view.sidebar.item(view._route_to_row["no_access"]).data(view.sidebar._ICON_ROLE) == Icons.LOCK
