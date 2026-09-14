"""Focused captures of real module navigation, with neutral business page bodies.

These are 768 px navigation crops, not full application screenshots or an
approved pixel baseline. Set SPJ_MODULE_SIDEBAR_ARTIFACTS to retain the captures.
"""
import hashlib
import os
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QPoint
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QLabel, QWidget

from frontend.desktop.components.icons import IconProvider
from frontend.desktop.themes.theme_manager import ThemeManager
from tests.ui.test_finance_hr_sidebar_icons import PageBody
from tests.ui.test_operational_sidebar_icons import SIDEBARS
from tests.ui.test_purchasing_sidebar_icons import PageBody as PurchasingPageBody
from tests.ui.test_purchasing_sidebar_icons import Presenter as PurchasingPresenter
from tests.ui.test_route_sidebar_icons import MODULES as ROUTE_MODULES


MODULES = (
    "finance", "hr", "products", "inventory", "pricing", "purchasing",
    *(entry[0] for entry in SIDEBARS),
    *(entry[0] for entry in ROUTE_MODULES),
)


def _build(module_name, monkeypatch):
    if module_name in {"finance", "hr"}:
        module = import_module(f"frontend.desktop.modules.{module_name}.{module_name}_view")
        monkeypatch.setattr(module, "_NAVIGATION", [
            (*entry[:2], PageBody, *entry[3:]) for entry in module._NAVIGATION
        ])
        view = getattr(module, "FinanceView" if module_name == "finance" else "HRView")(object())
        return view, view._nav

    if module_name == "products":
        from frontend.desktop.modules.products.composition import build_products_view

        pages = (
            ("overview_page", "ProductsOverviewPage"),
            ("product_catalog_page", "ProductCatalogPage"),
            ("categories_page", "ProductCategoriesPage"),
            ("brands_page", "ProductBrandsPage"),
            ("attributes_page", "ProductAttributesPage"),
            ("branch_channel_page", "BranchChannelPage"),
            ("import_page", "ProductImportPage"),
        )
        for name, class_name in pages:
            module = import_module(f"frontend.desktop.modules.products.pages.{name}")
            monkeypatch.setattr(module, class_name, lambda _presenter: QLabel(""))
        view = build_products_view(object())
        return view, view.nav

    if module_name == "inventory":
        from frontend.desktop.modules.inventory import page_registry
        from frontend.desktop.modules.inventory.inventory_view import InventoryView
        from frontend.desktop.modules.inventory.navigation import INVENTORY_NAV

        monkeypatch.setattr(page_registry, "_REAL_PAGES", {
            entry.page_id: lambda _presenter: QLabel("") for entry in INVENTORY_NAV
        })
        view = InventoryView(object(), page_registry.build_page_specs(lambda _permission: True))
        return view, view.nav

    if module_name == "pricing":
        from frontend.desktop.modules.pricing.pricing_workspace import PricingWorkspace

        view = PricingWorkspace(None, has_permission=lambda _permission: True,
                                page_builder=lambda _page_id, _presenter: QLabel(""))
        return view, view._nav

    if module_name == "purchasing":
        from frontend.desktop.modules.purchasing import purchasing_module_shell as module

        for name in ("ProcurementDashboardPage", "RequisitionsPage", "QuotationsPage", "OrdersPage",
                     "LogisticsRelatedPage", "PurchaseHistoryPage", "InvoicesPage"):
            monkeypatch.setattr(module, name, PurchasingPageBody)
        view = module.PurchasingModuleShell(PurchasingPresenter(), direct_purchase_views={
            "create": PurchasingPageBody(), "history": PurchasingPageBody()})
        return view, view.sidebar

    custom = dict(SIDEBARS)
    if module_name in custom:
        module = import_module(
            f"frontend.desktop.modules.{module_name}.widgets.{module_name}_sidebar_widget")
        nav = getattr(module, custom[module_name])(has_permission=lambda _permission: True)
        return nav, nav

    config = next(entry for entry in ROUTE_MODULES if entry[0] == module_name)
    name, class_name, routes_name, key, _icon, _examples = config
    route_module = import_module(f"frontend.desktop.modules.{name}.{name}_routes")
    module = import_module(f"frontend.desktop.modules.{name}.{name}_workspace")
    routes = getattr(route_module, routes_name)
    capabilities = SimpleNamespace(**dict.fromkeys(
        {"module_view", *(route.capability for route in routes)}, True))
    presenter = SimpleNamespace(
        capabilities=lambda: capabilities,
        status_cards=lambda: {"shift": "Sin turno", "sync": "Lista", "alerts": 0},
    )
    view = getattr(module, class_name)(presenter, page_factories={
        getattr(route, key): lambda parent: QWidget(parent) for route in routes
    })
    return view, view._nav


def _settle(app):
    for _ in range(4):
        app.processEvents()


def _save(widget, directory, name):
    directory.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.save(str(directory / f"{name}.png"))


@pytest.mark.parametrize("module_name", MODULES)
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["comfortable", "touch"])
def test_real_module_navigation_visuals(
        qt_font_resources, ui_tmp_path, monkeypatch, module_name, theme, density):
    app = qt_font_resources
    assert QFontDatabase().families(), "Real fonts are required for reviewable captures"
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, theme, density=density)
    owner, nav = _build(module_name, monkeypatch)
    directory = Path(os.environ.get("SPJ_MODULE_SIDEBAR_ARTIFACTS", str(ui_tmp_path)))
    label = f"{module_name}-{theme}-{density}"
    try:
        nav.setFixedHeight(768)
        owner.resize(nav.maximumWidth() if owner is nav else 1280, 768 if owner is nav else 900)
        owner.show()
        _settle(app)
        fingerprints = set()
        for row in range(nav.count()):
            item = nav.item(row)
            if item.data(nav._GROUP_ROLE):
                continue
            icon = item.data(nav._ICON_ROLE)
            assert icon, (module_name, row)
            pixels = item.icon().pixmap(32, 32).toImage()
            assert not pixels.isNull(), (module_name, row)
            assert pixels == IconProvider.icon(icon).pixmap(32, 32).toImage()
            fingerprints.add(hashlib.sha256(pixels.bits().asstring(pixels.byteCount())).hexdigest())
        assert len(fingerprints) > 1, "The sidebar must not repeat one glyph for every destination"
        for collapsed in (False, True):
            nav.set_collapsed(collapsed)
            nav.verticalScrollBar().setValue(0)
            _settle(app)
            assert nav.height() == 768
            _save(nav, directory, f"{label}-{'collapsed' if collapsed else 'expanded'}")
        groups = [row for row in range(nav.count()) if nav.item(row).data(nav._GROUP_ROLE)]
        if groups:
            # Include a real flyout with multiple destinations whenever available.
            selected = max(groups, key=lambda row: next(
                (end for end in groups if end > row), nav.count()) - row)
            menu = nav.group_menu(selected)
            try:
                assert menu.actions()
                assert all(not action.icon().isNull() for action in menu.actions())
                menu.popup(nav.mapToGlobal(QPoint(nav.width(), 0)))
                _settle(app)
                _save(menu, directory, f"{label}-flyout")
            finally:
                menu.close()
                sip.delete(menu)
    finally:
        owner.close()
        sip.delete(owner)
        app.sendPostedEvents(None, QEvent.DeferredDelete)
        _settle(app)
