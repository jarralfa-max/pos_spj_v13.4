import pytest

from backend.bootstrap.dependency_graph_validator import IssueSeverity
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.routing.errors import RouteGraphInvalidError
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.route_registry_validator import RouteRegistryValidator
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


@pytest.fixture
def modules() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(ModuleDescriptor(module_id="sales", display_name="Ventas"))
    return registry


@pytest.fixture
def view_factories() -> ViewFactoryRegistry:
    registry = ViewFactoryRegistry()
    registry.register("sales.pos_view", lambda: object())
    return registry


def _route(route_id, **overrides) -> RouteDefinition:
    kwargs = dict(module_id="sales", title=route_id, view_factory_id="sales.pos_view")
    kwargs.update(overrides)
    return RouteDefinition(route_id=route_id, **kwargs)


def test_valid_graph_has_no_issues(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("sales.pos"))
    assert RouteRegistryValidator().validate(routes, modules, view_factories) == []


def test_unknown_module_id_is_an_error(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("sales.pos", module_id="unknown_module"))
    issues = RouteRegistryValidator().validate(routes, modules, view_factories)
    assert any(i.code == "ROUTE_MODULE_NOT_FOUND" for i in issues)
    assert all(i.severity is IssueSeverity.ERROR for i in issues if i.code == "ROUTE_MODULE_NOT_FOUND")


def test_unknown_view_factory_id_is_an_error(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("sales.pos", view_factory_id="does_not_exist"))
    issues = RouteRegistryValidator().validate(routes, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


@pytest.mark.parametrize("ambiguous_id", ["POS", "CAJA", "PRODUCCION", "CONFIGURACION", "pos"])
def test_legacy_ambiguous_codes_are_rejected(modules, view_factories, ambiguous_id):
    routes = RouteRegistry()
    routes.register(_route(ambiguous_id))
    issues = RouteRegistryValidator().validate(routes, modules, view_factories)
    assert any(i.code == "AMBIGUOUS_ROUTE_ID" for i in issues)


def test_route_id_without_dot_is_ambiguous(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("someroute"))
    issues = RouteRegistryValidator().validate(routes, modules, view_factories)
    assert any(i.code == "AMBIGUOUS_ROUTE_ID" for i in issues)


def test_dotted_route_id_is_not_flagged_as_ambiguous(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("sales.pos"))
    issues = RouteRegistryValidator().validate(routes, modules, view_factories)
    assert not any(i.code == "AMBIGUOUS_ROUTE_ID" for i in issues)


def test_multiple_routes_report_every_issue_at_once(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("POS", module_id="unknown"))
    routes.register(_route("sales.other", view_factory_id="missing"))
    issues = RouteRegistryValidator().validate(routes, modules, view_factories)
    codes = {i.code for i in issues}
    assert "AMBIGUOUS_ROUTE_ID" in codes
    assert "ROUTE_MODULE_NOT_FOUND" in codes
    assert "ROUTE_VIEW_FACTORY_NOT_FOUND" in codes


def test_validate_or_raise_passes_silently_on_valid_graph(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("sales.pos"))
    RouteRegistryValidator().validate_or_raise(routes, modules, view_factories)  # must not raise


def test_validate_or_raise_raises_with_all_errors(modules, view_factories):
    routes = RouteRegistry()
    routes.register(_route("POS", module_id="unknown", view_factory_id="missing"))
    with pytest.raises(RouteGraphInvalidError) as exc:
        RouteRegistryValidator().validate_or_raise(routes, modules, view_factories)
    assert len(exc.value.issues) == 3


def test_empty_route_registry_is_always_valid(modules, view_factories):
    assert RouteRegistryValidator().validate(RouteRegistry(), modules, view_factories) == []
