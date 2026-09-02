from backend.bootstrap.application_context import FeatureContext
from frontend.desktop.components.icons import Icons
from frontend.desktop.shell.sidebar.badge_registry import BadgeRegistry
from frontend.desktop.shell.sidebar.navigation_item_definition import NavigationItemDefinition
from frontend.desktop.shell.sidebar.navigation_item_registry import NavigationItemRegistry
from frontend.desktop.shell.sidebar.sidebar_resolver import SidebarResolver
from tests.unit.shell.sidebar.conftest import healthy_report, make_context


def _nav_item(item_id="nav.sales.pos", **overrides) -> NavigationItemDefinition:
    kwargs = dict(module_id="sales", route_id="sales.pos", label="Punto de Venta", icon=Icons.SALES)
    kwargs.update(overrides)
    return NavigationItemDefinition(item_id=item_id, **kwargs)


def _resolver(routes, modules, *, nav_items=None, badges=None) -> SidebarResolver:
    registry = nav_items or NavigationItemRegistry()
    return SidebarResolver(
        navigation_items=registry, route_registry=routes, module_registry=modules, badge_registry=badges,
    )


def test_resolves_a_valid_item(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item())
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())
    assert [i.item_id for i in result] == ["nav.sales.pos"]


def test_item_with_unknown_route_id_is_dropped(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(route_id="does.not_exist"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())
    assert result == ()


def test_item_with_unknown_module_id_is_dropped(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(module_id="does_not_exist"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())
    assert result == ()


def test_item_whose_module_fails_health_requirement_is_dropped(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(
        item_id="nav.inventory.overview", module_id="inventory", route_id="inventory.overview",
    ))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())  # no "database" check
    assert result == ()


def test_item_whose_module_satisfies_health_requirement_is_kept(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(
        item_id="nav.inventory.overview", module_id="inventory", route_id="inventory.overview",
    ))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report("database"))
    assert [i.item_id for i in result] == ["nav.inventory.overview"]


def test_item_requiring_permission_the_context_lacks_is_dropped(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(required_permission="SALES.ELIMINAR"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    context = make_context(permissions=frozenset({"SALES.VER"}))
    result = resolver.resolve(context=context, health_report=healthy_report())
    assert result == ()


def test_item_requiring_permission_the_context_has_is_kept(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(required_permission="SALES.VER"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    context = make_context(permissions=frozenset({"SALES.VER"}))
    result = resolver.resolve(context=context, health_report=healthy_report())
    assert [i.item_id for i in result] == ["nav.sales.pos"]


def test_admin_bypasses_required_permission(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(required_permission="SALES.ELIMINAR"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    context = make_context(permissions=frozenset(), roles=("admin",))
    result = resolver.resolve(context=context, health_report=healthy_report())
    assert [i.item_id for i in result] == ["nav.sales.pos"]


def test_item_behind_disabled_feature_flag_is_dropped(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(feature_flag="new_pos_ui"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())
    assert result == ()


def test_item_behind_enabled_feature_flag_is_kept(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(feature_flag="new_pos_ui"))
    resolver = _resolver(routes, modules, nav_items=nav_items)
    context = make_context(feature_context=FeatureContext(enabled_features=frozenset({"new_pos_ui"})))
    result = resolver.resolve(context=context, health_report=healthy_report())
    assert [i.item_id for i in result] == ["nav.sales.pos"]


def test_is_active_true_for_current_route(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item())
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report(), current_route_id="sales.pos")
    assert result[0].is_active is True


def test_is_active_false_for_a_different_route(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item())
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(
        context=make_context(), health_report=healthy_report(), current_route_id="inventory.overview",
    )
    assert result[0].is_active is False


def test_badge_count_comes_from_registered_source(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item(badge_key="sales.pending"))
    badges = BadgeRegistry()
    badges.register("sales.pending", lambda: 4)
    resolver = _resolver(routes, modules, nav_items=nav_items, badges=badges)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())
    assert result[0].badge_count == 4


def test_badge_count_is_none_when_item_has_no_badge_key(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item())
    resolver = _resolver(routes, modules, nav_items=nav_items)
    result = resolver.resolve(context=make_context(), health_report=healthy_report())
    assert result[0].badge_count is None


def test_active_item_id_for_route_finds_the_owning_item(routes, modules):
    nav_items = NavigationItemRegistry()
    nav_items.register(_nav_item())
    resolver = _resolver(routes, modules, nav_items=nav_items)
    assert resolver.active_item_id_for_route("sales.pos") == "nav.sales.pos"


def test_active_item_id_for_route_returns_none_for_unmatched_route(routes, modules):
    resolver = _resolver(routes, modules)
    assert resolver.active_item_id_for_route("sales.pos") is None


def test_active_item_id_for_route_returns_none_for_none_input(routes, modules):
    resolver = _resolver(routes, modules)
    assert resolver.active_item_id_for_route(None) is None
