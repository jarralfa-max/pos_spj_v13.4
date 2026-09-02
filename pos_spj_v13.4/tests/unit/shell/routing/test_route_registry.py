import pytest

from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.errors import DuplicateRouteRegistrationError, RouteNotFoundError
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry


def _route(route_id, **overrides) -> RouteDefinition:
    kwargs = dict(module_id="sales", title=route_id, view_factory_id=f"{route_id}_view")
    kwargs.update(overrides)
    return RouteDefinition(route_id=route_id, **kwargs)


def test_register_and_get():
    registry = RouteRegistry()
    registry.register(_route("sales.pos"))
    assert registry.get("sales.pos").module_id == "sales"


def test_is_registered():
    registry = RouteRegistry()
    assert registry.is_registered("sales.pos") is False
    registry.register(_route("sales.pos"))
    assert registry.is_registered("sales.pos") is True


def test_get_returns_none_for_unknown_route():
    registry = RouteRegistry()
    assert registry.get("nope") is None


def test_require_raises_for_unknown_route():
    registry = RouteRegistry()
    with pytest.raises(RouteNotFoundError):
        registry.require("nope")


def test_duplicate_route_id_raises():
    registry = RouteRegistry()
    registry.register(_route("sales.pos"))
    with pytest.raises(DuplicateRouteRegistrationError):
        registry.register(_route("sales.pos"))


def test_all_returns_every_registered_route():
    registry = RouteRegistry()
    registry.register(_route("sales.pos"))
    registry.register(_route("inventory.overview", module_id="inventory"))
    assert {r.route_id for r in registry.all()} == {"sales.pos", "inventory.overview"}


def test_by_module_id_filters_correctly():
    registry = RouteRegistry()
    registry.register(_route("sales.pos"))
    registry.register(_route("sales.returns"))
    registry.register(_route("inventory.overview", module_id="inventory"))

    sales_routes = registry.by_module_id("sales")
    assert {r.route_id for r in sales_routes} == {"sales.pos", "sales.returns"}


def test_by_startup_mode_filters_correctly():
    registry = RouteRegistry()
    registry.register(_route("dashboard.overview", startup_mode=StartupMode.EAGER))
    registry.register(_route("finance.dashboard", startup_mode=StartupMode.LAZY))

    eager = registry.by_startup_mode(StartupMode.EAGER)
    assert {r.route_id for r in eager} == {"dashboard.overview"}
