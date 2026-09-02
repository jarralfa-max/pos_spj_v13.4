from frontend.desktop.shell.sidebar.sidebar_item_view_model import SidebarItemViewModel
from frontend.desktop.shell.sidebar.sidebar_search import filter_sidebar_items


def _vm(item_id, label, group="") -> SidebarItemViewModel:
    return SidebarItemViewModel(
        item_id=item_id, route_id=f"{item_id}.route", label=label, icon="icon",
        group=group, order=0, badge_count=None, is_active=False,
    )


def test_empty_query_returns_all_items():
    items = (_vm("a", "Ventas"), _vm("b", "Inventario"))
    assert filter_sidebar_items(items, "") == items


def test_whitespace_only_query_returns_all_items():
    items = (_vm("a", "Ventas"),)
    assert filter_sidebar_items(items, "   ") == items


def test_matches_label_case_insensitively():
    items = (_vm("a", "Ventas"), _vm("b", "Inventario"))
    result = filter_sidebar_items(items, "VENTAS")
    assert [i.item_id for i in result] == ["a"]


def test_matches_label_substring():
    items = (_vm("a", "Punto de Venta"),)
    result = filter_sidebar_items(items, "venta")
    assert [i.item_id for i in result] == ["a"]


def test_matches_group_name():
    items = (_vm("a", "Punto de Venta", group="Operación"), _vm("b", "Nómina", group="RRHH"))
    result = filter_sidebar_items(items, "rrhh")
    assert [i.item_id for i in result] == ["b"]


def test_no_match_returns_empty_tuple():
    items = (_vm("a", "Ventas"),)
    assert filter_sidebar_items(items, "zzz") == ()
