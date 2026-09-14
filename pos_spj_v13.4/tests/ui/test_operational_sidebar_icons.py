"""Real module navigation must render its declared icon without losing routes."""
from importlib import import_module

import pytest
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture
def manager(qt_font_resources, monkeypatch):
    instance = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", instance)
    instance.apply(qt_font_resources, "light")
    yield instance
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


def assert_icon(item, identifier):
    assert not item.icon().isNull(), identifier
    for mode in (QIcon.Normal, QIcon.Selected, QIcon.Disabled):
        actual = item.icon().pixmap(32, 32, mode).toImage()
        expected = IconProvider.icon(identifier).pixmap(32, 32, mode).toImage()
        assert actual == expected, identifier


SIDEBARS = (
    ("losses", "LossesSidebarWidget"),
    ("meat_processing", "MeatProcessingSidebarWidget"),
    ("orders_delivery", "OrdersDeliverySidebarWidget"),
    ("business_intelligence", "BusinessIntelligenceSidebarWidget"),
    ("transfers", "TransfersSidebarWidget"),
    ("configuracion", "ConfiguracionSidebarWidget"),
)


@pytest.mark.parametrize("module,class_name", SIDEBARS)
@pytest.mark.parametrize("filtered", [False, True])
def test_custom_sidebar_icons_preserve_permissions_badges_and_route_signals(
    manager, qt_font_resources, module, class_name, filtered,
):
    root = f"frontend.desktop.modules.{module}"
    navigation = import_module(f"{root}.navigation.{module}_sidebar")
    sidebar_class = getattr(import_module(f"{root}.widgets.{module}_sidebar_widget"), class_name)
    all_entries = navigation.visible_entries(lambda _permission: True)
    denied = all_entries[0][0].permission if filtered else None
    allowed = lambda permission: permission != denied
    badges = {entry.badge_key: 3 for entry, _ in all_entries if entry.badge_key}
    expected = navigation.visible_entries(allowed, badges)
    sidebar = sidebar_class(has_permission=allowed, badges=badges)
    try:
        assert sidebar.count() == len(expected)
        assert sidebar.currentRow() == 0
        routes = []
        sidebar.route_requested.connect(routes.append)
        for theme in ("light", "dark"):
            manager.set_theme(theme, app=qt_font_resources)
            for row, (entry, badge) in enumerate(expected):
                item = sidebar.item(row)
                assert item.data(Qt.UserRole) == entry.page_id
                assert item.toolTip() == entry.tooltip
                assert item.text() == (entry.title if badge is None else f"{entry.title} ({badge})")
                assert_icon(item, entry.icon)
        sidebar.setCurrentRow(1)
        assert routes == [expected[1][0].page_id]
        if hasattr(sidebar, "set_collapsed"):
            sidebar.set_collapsed(True)
            for row, (entry, _badge) in enumerate(expected):
                assert sidebar.item(row).text() == ""
                assert sidebar.item(row).data(Qt.AccessibleTextRole)
                assert_icon(sidebar.item(row), entry.icon)
            sidebar.set_collapsed(False)
            assert sidebar.currentRow() == 1
            assert routes == [expected[1][0].page_id]
    finally:
        sidebar.deleteLater()


@pytest.mark.parametrize("filtered", [False, True])
def test_inventory_icons_follow_filtered_registry_without_reordering_pages(
    manager, qt_font_resources, monkeypatch, filtered,
):
    from frontend.desktop.modules.inventory import page_registry
    from frontend.desktop.modules.inventory.inventory_view import InventoryView
    from frontend.desktop.modules.inventory.navigation import INVENTORY_NAV, visible_entries

    denied = INVENTORY_NAV[0].permission if filtered else None
    allowed = lambda permission: permission != denied
    entries = visible_entries(allowed)
    built = []

    def factory(entry):
        def build(_presenter):
            built.append(entry.page_id)
            return QLabel(entry.page_id)
        return build

    monkeypatch.setattr(page_registry, "_REAL_PAGES", {
        entry.page_id: factory(entry) for entry in INVENTORY_NAV
    })
    view = InventoryView(object(), page_registry.build_page_specs(allowed))
    try:
        assert built == [entries[0].page_id]
        assert view.nav.count() == len(entries)
        for theme in ("light", "dark"):
            manager.set_theme(theme, app=qt_font_resources)
            for row, entry in enumerate(entries):
                assert view.nav.item(row).text() == entry.title
                assert_icon(view.nav.item(row), entry.icon)
        view.nav.select(1)
        assert view.stack.currentIndex() == 1
        assert built == [entries[0].page_id, entries[1].page_id]
    finally:
        view.deleteLater()


@pytest.mark.parametrize("filtered", [False, True])
def test_pricing_icons_follow_visible_routes_and_keep_lazy_navigation(
    manager, qt_font_resources, filtered,
):
    from frontend.desktop.modules.pricing.navigation import PRICING_NAV, visible_entries
    from frontend.desktop.modules.pricing.pricing_workspace import PricingWorkspace

    denied = PRICING_NAV[0].permission if filtered else None
    allowed = lambda permission: permission != denied
    entries = visible_entries(allowed)
    built = []

    def build(page_id, _presenter):
        built.append(page_id)
        return QLabel(page_id)

    view = PricingWorkspace(None, has_permission=allowed, page_builder=build)
    try:
        assert built == [entries[0].page_id]
        for theme in ("light", "dark"):
            manager.set_theme(theme, app=qt_font_resources)
            for row, entry in enumerate(entries):
                assert view._nav.item(row).text() == entry.title
                assert_icon(view._nav.item(row), entry.icon)
        view._nav.select(1)
        assert view.active_page_id == entries[1].page_id
        assert built == [entries[0].page_id, entries[1].page_id]
    finally:
        view.deleteLater()


def test_products_real_composition_has_distinct_section_icons(manager, qt_font_resources, monkeypatch):
    from frontend.desktop.modules.products.composition import build_products_view
    from frontend.desktop.modules.products.navigation import PRODUCTS_NAV

    pages = (
        ("overview_page", "ProductsOverviewPage", "Resumen"),
        ("product_catalog_page", "ProductCatalogPage", "Catálogo"),
        ("categories_page", "ProductCategoriesPage", "Categorías"),
        ("brands_page", "ProductBrandsPage", "Marcas"),
        ("attributes_page", "ProductAttributesPage", "Atributos"),
        ("branch_channel_page", "BranchChannelPage", "Sucursales y canales"),
        ("import_page", "ProductImportPage", "Importar"),
    )
    built = []

    def factory(title):
        def build(_presenter):
            built.append(title)
            return QLabel(title)
        return build

    for module, name, title in pages:
        monkeypatch.setattr(import_module(f"frontend.desktop.modules.products.pages.{module}"),
                            name, factory(title))
    metadata = {entry.page_id: entry for entry in PRODUCTS_NAV}
    icons = (
        metadata["products_overview"].icon,
        metadata["products_catalog"].icon,
        metadata["products_categories"].icon,
        Icons.COMPANY,
        Icons.CHECKLIST,
        metadata["products_branches"].icon,
        metadata["products_imports"].icon,
    )
    view = build_products_view(object())
    try:
        assert view.nav.count() == len(pages)
        assert built == [pages[0][2]]
        for theme in ("light", "dark"):
            manager.set_theme(theme, app=qt_font_resources)
            for row, ((_module, _name, title), icon) in enumerate(zip(pages, icons)):
                assert view.nav.item(row).text() == title
                assert_icon(view.nav.item(row), icon)
        view.nav.select(6)
        assert view.stack.currentIndex() == 6
        assert built == [pages[0][2], pages[6][2]]
    finally:
        view.deleteLater()
