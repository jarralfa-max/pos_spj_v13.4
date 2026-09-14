"""Exercise route-driven module sidebars with real Qt and neutral page factories."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QScrollArea, QWidget

from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.themes.theme_manager import ThemeManager


MODULES = (
    ("cash_register", "CashRegisterWorkspace", "CASH_REGISTER_ROUTES", "key", Icons.CASH,
     {"overview": Icons.DASHBOARD, "ledger": Icons.MOVEMENTS,
      "hardware": Icons.DEVICE, "configuration": Icons.SETTINGS}),
    ("customers_crm", "CustomersCrmWorkspace", "CUSTOMER_CRM_ROUTES", "route_id", Icons.CUSTOMERS,
     {"customers.directory": Icons.CUSTOMERS, "customers.create": Icons.ADD,
      "crm.calls": Icons.PHONE, "customers.settings": Icons.SETTINGS}),
    ("fidelidad", "FidelidadWorkspace", "FIDELIDAD_ROUTES", "route_id", Icons.LOYALTY,
     {"loyalty.member_profile": Icons.USER, "loyalty.birthdays": Icons.CALENDAR,
      "fidelidad.fraud": Icons.INVESTIGATION, "fidelidad.settings": Icons.SETTINGS}),
    ("tarjetas_fidelidad", "TarjetasFidelidadWorkspace", "TARJETAS_FIDELIDAD_ROUTES", "route_id", Icons.LOYALTY_CARDS,
     {"tarjetas.cards": Icons.LOYALTY_CARDS, "tarjetas.designer": Icons.EDIT,
      "tarjetas.printing": Icons.PRINT}),
    ("assets", "AssetsWorkspace", "ASSET_ROUTES", "route_id", Icons.ASSETS,
     {"assets.directory": Icons.ASSETS, "assets.locations": Icons.LOCATION,
      "assets.maintenance.calendar": Icons.CALENDAR, "assets.audit": Icons.AUDIT}),
)


@pytest.fixture(params=MODULES, ids=lambda config: config[0])
def workspace_case(request, qt_font_resources, monkeypatch):
    module, class_name, routes_name, key, module_icon, examples = request.param
    route_module = import_module(f"frontend.desktop.modules.{module}.{module}_routes")
    workspace_module = import_module(f"frontend.desktop.modules.{module}.{module}_workspace")
    routes = getattr(route_module, routes_name)
    capabilities = SimpleNamespace(**dict.fromkeys(
        {"module_view", *(route.capability for route in routes)}, True))
    presenter = SimpleNamespace(
        capabilities=lambda: capabilities,
        status_cards=lambda: {"shift": "Sin turno", "sync": "Lista", "alerts": 0},
    )
    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light")

    def factory(route_id):
        def make(parent):
            page = QWidget(parent)
            page.setProperty("testRoute", route_id)
            return page
        return make

    workspace = getattr(workspace_module, class_name)(presenter, page_factories={
        getattr(route, key): factory(getattr(route, key)) for route in routes
    })
    try:
        yield SimpleNamespace(
            workspace=workspace, routes=routes, route_module=route_module,
            key=key, capabilities=capabilities, manager=manager,
            module_icon=module_icon, examples=examples, app=qt_font_resources,
        )
    finally:
        sip.delete(workspace)
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)
        qt_font_resources.processEvents()


def _destinations(nav):
    return [nav.item(row) for row in range(nav.count())
            if not nav.item(row).data(nav._GROUP_ROLE)]


def _image(icon):
    return icon.pixmap(32, 32, QIcon.Normal, QIcon.Off).toImage()


def _pixels(icon):
    image = _image(icon)
    return image.constBits().asstring(image.byteCount())


def test_route_icons_survive_theme_collapse_and_flyout_navigation(workspace_case):
    case = workspace_case
    nav = case.workspace._nav
    routes_by_id = {getattr(route, case.key): route for route in case.routes}
    for route_id, icon in case.examples.items():
        item = next(item for item in _destinations(nav) if item.data(Qt.UserRole) == route_id)
        assert item.data(nav._ICON_ROLE) == icon
    assert len({_pixels(item.icon()) for item in _destinations(nav)}) > 1

    for theme in ("light", "dark"):
        case.manager.set_theme(theme, app=case.app)
        for collapsed in (False, True):
            nav.set_collapsed(collapsed)
            items = _destinations(nav)
            assert [item.data(Qt.UserRole) for item in items] == list(routes_by_id)
            for item in items:
                route = routes_by_id[item.data(Qt.UserRole)]
                assert item.data(nav._ICON_ROLE) == route.icon
                assert item.icon().isNull() is False
                assert _image(item.icon()) == _image(IconProvider.icon(route.icon))
                assert item.flags() & Qt.ItemIsEnabled
                assert item.toolTip() == route.tooltip
                assert item.data(Qt.AccessibleDescriptionRole) == route.tooltip
                assert item.text() == ("" if collapsed else route.label)

            for row in range(nav.count()):
                item = nav.item(row)
                if not item.data(nav._GROUP_ROLE):
                    continue
                group = item.data(nav._BASE_LABEL_ROLE)
                assert item.data(nav._ICON_ROLE) == case.route_module.GROUP_ICONS[group]
                if collapsed:
                    assert _image(item.icon()) == _image(IconProvider.icon(case.route_module.GROUP_ICONS[group]))
                menu = nav.group_menu(row)
                try:
                    child_row = row + 1
                    for action in menu.actions():
                        child = nav.item(child_row)
                        route = routes_by_id[child.data(Qt.UserRole)]
                        assert _image(action.icon()) == _image(IconProvider.icon(route.icon))
                        action.trigger()
                        active = case.workspace._stack.currentWidget().findChild(QScrollArea).widget()
                        assert active.property("testRoute") == getattr(route, case.key)
                        child_row += 1
                finally:
                    sip.delete(menu)


def test_sibling_routes_render_different_shapes(workspace_case):
    """Different identifiers alone do not protect against aliases to one glyph."""
    case = workspace_case
    for theme in ("light", "dark"):
        case.manager.set_theme(theme, app=case.app)
        by_group = case.route_module.grouped_routes(case.routes)
        for group, routes in by_group:
            pixels = {_pixels(IconProvider.icon(route.icon)) for route in routes}
            assert len(pixels) == len(routes), f"Repeated icon shape in {group} ({theme})"


def test_permission_refresh_keeps_allowed_routes_icons_and_destination(workspace_case):
    case = workspace_case
    selected = case.routes[-1]
    case.workspace.select_route(getattr(selected, case.key))
    for name in vars(case.capabilities):
        setattr(case.capabilities, name, name in {"module_view", selected.capability})
    case.workspace.refresh_permissions()
    nav = case.workspace._nav
    expected = case.route_module.visible_routes(case.capabilities)
    assert [item.data(Qt.UserRole) for item in _destinations(nav)] == [getattr(route, case.key) for route in expected]
    for item, route in zip(_destinations(nav), expected):
        assert item.data(nav._ICON_ROLE) == route.icon
    active = case.workspace._stack.currentWidget().findChild(QScrollArea).widget()
    assert active.property("testRoute") == getattr(selected, case.key)


def test_no_permission_group_uses_module_icon_without_exposing_routes(workspace_case):
    case = workspace_case
    case.capabilities.module_view = False
    case.workspace.refresh_permissions()
    nav = case.workspace._nav
    assert nav.count() == 1
    assert nav.item(0).data(nav._GROUP_ROLE)
    assert nav.item(0).data(nav._ICON_ROLE) == case.module_icon
    assert nav.item(0).data(Qt.UserRole) is None
    assert case.workspace._stack.count() == 1
