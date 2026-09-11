"""Protection for navigation state, shell actions and official asset policy."""
from PyQt5.QtCore import QSettings, Qt

from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.shell.application_shell.top_bar import TopBar
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from tests.ui.shell.conftest import make_context
from tests.ui.shell.test_global_sidebar import _vm


def test_sidebar_collapse_restores_route_and_keeps_toggle_reachable(tmp_path):
    settings = QSettings(str(tmp_path / "navigation.ini"), QSettings.IniFormat)
    items = (_vm("sales", "sales.pos", "Ventas"), _vm("stock", "inventory.overview", "Inventario"))
    sidebar = GlobalSidebar(settings=settings, settings_key="user-one")
    sidebar.set_items(items)
    sidebar.set_active_route("inventory.overview")
    sidebar.set_collapsed(True)
    assert sidebar.maximumWidth() <= 64
    assert not sidebar._toggle.isHidden()
    assert sidebar._nav.item(1).text() == ""
    assert sidebar._nav.item(1).toolTip() == "Inventario"
    assert not sidebar._nav.item(1).icon().isNull()

    restored = GlobalSidebar(settings=settings, settings_key="user-one")
    restored.set_items(items)
    assert restored.collapsed
    assert restored.active_route == "inventory.overview"
    assert restored._nav.currentRow() == 1
    restored._on_search_changed("ventas")
    restored._on_search_changed("")
    assert restored._nav.currentRow() == 1


def test_sidebar_search_render_does_not_emit_navigation():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Ventas"), _vm("b", "inventory.overview", "Inventario")))
    sidebar.set_active_route("inventory.overview")
    calls = []
    sidebar.item_activated.connect(calls.append)
    sidebar._on_search_changed("ventas")
    sidebar._on_search_changed("")
    assert calls == []
    assert sidebar.active_route == "inventory.overview"


def test_module_group_collapses_without_changing_route_indices():
    nav = SideNav()
    nav.add_group("Tesorería")
    nav.add_section("Cuentas")
    nav.add_section("Conciliación")
    nav.add_group("Cobranza")
    nav.add_section("Clientes")
    nav.toggle_group(0)
    assert nav.item(1).isHidden()
    assert nav.item(2).isHidden()
    assert not nav.item(4).isHidden()
    nav.select(2)
    assert not nav.item(2).isHidden()
    assert nav.currentRow() == 2
    nav.set_collapsed(True)
    menu = nav.group_menu(0)
    assert [action.text() for action in menu.actions()] == ["Cuentas", "Conciliación"]
    selected = []
    nav.navigated.connect(selected.append)
    menu.actions()[0].trigger()
    assert selected == [1]


def test_topbar_actions_and_session_are_accessible():
    bar = TopBar()
    bar.set_context(make_context(user_name="Ana Ruiz", offline_status="OFFLINE"))
    assert "Ana Ruiz" in bar.context_text
    assert bar.session_text == "Sin conexión"
    assert "Cerrar sesión" in [action.text() for action in bar.file_menu.actions()]
    received = []
    bar.logout_requested.connect(lambda: received.append("logout"))
    bar.logout_action.trigger()
    assert received == ["logout"]
    bar.set_unread_notification_count(3)
    assert bar._notification_badge.text() == "3"
    assert not bar._notification_badge.isHidden()
    bar.set_unread_notification_count(-1)
    assert bar.unread_notification_count == 0
    assert bar._notification_badge.isHidden()
    assert bar._settings_button.accessibleName()
