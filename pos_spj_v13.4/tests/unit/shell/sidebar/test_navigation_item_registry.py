import pytest

from frontend.desktop.components.icons import Icons
from frontend.desktop.shell.sidebar.errors import (
    DuplicateNavigationItemRegistrationError,
    NavigationItemNotFoundError,
)
from frontend.desktop.shell.sidebar.navigation_item_definition import NavigationItemDefinition
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry


def _item(item_id, **overrides) -> NavigationItemDefinition:
    kwargs = dict(module_id="sales", route_id=f"{item_id}_route", label=item_id, icon=Icons.SALES)
    kwargs.update(overrides)
    return NavigationItemDefinition(item_id=item_id, **kwargs)


def test_register_and_get():
    registry = NavigationItemRegistry()
    registry.register(_item("nav.a"))
    assert registry.get("nav.a").module_id == "sales"


def test_is_registered():
    registry = NavigationItemRegistry()
    assert registry.is_registered("nav.a") is False
    registry.register(_item("nav.a"))
    assert registry.is_registered("nav.a") is True


def test_get_returns_none_for_unknown_id():
    registry = NavigationItemRegistry()
    assert registry.get("nope") is None


def test_require_raises_for_unknown_id():
    registry = NavigationItemRegistry()
    with pytest.raises(NavigationItemNotFoundError):
        registry.require("nope")


def test_duplicate_item_id_raises():
    registry = NavigationItemRegistry()
    registry.register(_item("nav.a"))
    with pytest.raises(DuplicateNavigationItemRegistrationError):
        registry.register(_item("nav.a"))


def test_all_returns_items_sorted_by_group_then_order_then_label():
    registry = NavigationItemRegistry()
    registry.register(_item("nav.c", label="Zeta", group="B", order=1))
    registry.register(_item("nav.a", label="Alfa", group="A", order=2))
    registry.register(_item("nav.b", label="Beta", group="A", order=1))
    ordered = [i.item_id for i in registry.all()]
    assert ordered == ["nav.b", "nav.a", "nav.c"]


def test_by_module_id_filters_correctly():
    registry = NavigationItemRegistry()
    registry.register(_item("nav.a", module_id="sales"))
    registry.register(_item("nav.b", module_id="inventory"))
    assert {i.item_id for i in registry.by_module_id("sales")} == {"nav.a"}


def test_by_group_filters_correctly():
    registry = NavigationItemRegistry()
    registry.register(_item("nav.a", group="Operacion"))
    registry.register(_item("nav.b", group="Administracion"))
    assert {i.item_id for i in registry.by_group("Operacion")} == {"nav.a"}


def test_item_for_route_finds_matching_item():
    registry = NavigationItemRegistry()
    registry.register(_item("nav.a", route_id="sales.pos"))
    item = registry.item_for_route("sales.pos")
    assert item.item_id == "nav.a"


def test_item_for_route_returns_none_when_unmatched():
    registry = NavigationItemRegistry()
    assert registry.item_for_route("nope") is None
