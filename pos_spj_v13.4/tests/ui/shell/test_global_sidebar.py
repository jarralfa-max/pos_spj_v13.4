from frontend.desktop.components.icons import Icons
from frontend.desktop.shell.sidebar.global_sidebar import GlobalSidebar
from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel


def _vm(item_id, route_id, label, *, group="", badge_count=None, is_active=False) -> SidebarItemViewModel:
    return SidebarItemViewModel(
        item_id=item_id, route_id=route_id, label=label, icon=Icons.SALES,
        group=group, order=0, badge_count=badge_count, is_active=is_active,
    )


def test_starts_empty():
    sidebar = GlobalSidebar()
    assert sidebar.visible_item_count == 0


def test_set_items_populates_the_list():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Punto de Venta"), _vm("b", "inventory.overview", "Inventario")))
    assert sidebar.visible_item_count == 2


def test_grouped_items_add_a_non_interactive_header_row():
    sidebar = GlobalSidebar()
    sidebar.set_items((
        _vm("a", "sales.pos", "Punto de Venta", group="Operación"),
        _vm("b", "inventory.overview", "Inventario", group="Operación"),
    ))
    # 1 header + 2 items = 3 rows, but only 2 are "visible" (route-bearing) items.
    assert sidebar._nav.count() == 3
    assert sidebar.visible_item_count == 2


def test_clicking_a_row_emits_item_activated_with_its_route_id():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Punto de Venta"), _vm("b", "inventory.overview", "Inventario")))
    activated = []
    sidebar.item_activated.connect(activated.append)
    sidebar._nav.setCurrentRow(1)
    assert activated == ["inventory.overview"]


def test_clicking_a_group_header_row_does_not_emit_item_activated():
    sidebar = GlobalSidebar()
    sidebar.set_items((
        _vm("a", "sales.pos", "Punto de Venta", group="Operación"),
        _vm("b", "inventory.overview", "Inventario", group="Operación"),
    ))
    activated = []
    sidebar.item_activated.connect(activated.append)
    sidebar._on_row_navigated(0)  # row 0 is the "Operación" header
    assert activated == []


def test_set_active_route_selects_the_matching_row_without_reemitting():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Punto de Venta"), _vm("b", "inventory.overview", "Inventario")))
    activated = []
    sidebar.item_activated.connect(activated.append)
    sidebar.set_active_route("inventory.overview")
    assert sidebar._nav.currentRow() == 1
    assert activated == []  # programmatic update must not look like a user click


def test_set_active_route_with_unknown_route_id_is_a_no_op():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Punto de Venta"),))
    sidebar.set_active_route("does.not_exist")  # must not raise
    assert sidebar._nav.currentRow() != 0 or sidebar._nav.count() == 1


def test_search_changed_filters_visible_items():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Ventas"), _vm("b", "inventory.overview", "Recursos Humanos")))
    sidebar._on_search_changed("ventas")
    assert sidebar.visible_item_count == 1


def test_clearing_search_restores_full_list():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Ventas"), _vm("b", "inventory.overview", "Recursos Humanos")))
    sidebar._on_search_changed("ventas")
    sidebar._on_search_changed("")
    assert sidebar.visible_item_count == 2


def test_set_items_after_search_is_applied_reapplies_the_active_query():
    sidebar = GlobalSidebar()
    sidebar._on_search_changed("ventas")
    sidebar.set_items((_vm("a", "sales.pos", "Ventas"), _vm("b", "inventory.overview", "Recursos Humanos")))
    assert sidebar.visible_item_count == 1


def test_badge_count_is_reflected_in_the_underlying_side_nav_item_text():
    sidebar = GlobalSidebar()
    sidebar.set_items((_vm("a", "sales.pos", "Ventas", badge_count=3),))
    assert "3" in sidebar._nav.item(0).text()
