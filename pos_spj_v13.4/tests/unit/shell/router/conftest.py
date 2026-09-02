import pytest

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def make_context(**overrides) -> ApplicationContext:
    fields = dict(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Jose Alfaro", roles=("cajero",),
        permissions=frozenset({"SALES.VER"}), feature_context=FeatureContext(),
        session_id="session-1",
    )
    fields.update(overrides)
    return ApplicationContext(**fields)


@pytest.fixture
def context() -> ApplicationContext:
    return make_context()


@pytest.fixture
def view_factories() -> ViewFactoryRegistry:
    registry = ViewFactoryRegistry()
    registry.register("sales.pos_view", lambda: {"widget": "pos"})
    registry.register("inventory.overview_view", lambda: {"widget": "inventory"})
    registry.register("whatsapp.status_view", lambda: {"widget": "whatsapp"})
    return registry


@pytest.fixture
def routes() -> RouteRegistry:
    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="sales.pos", module_id="sales", title="Punto de Venta",
        view_factory_id="sales.pos_view", required_permission="SALES.ver",
    ))
    registry.register(RouteDefinition(
        route_id="inventory.overview", module_id="inventory", title="Inventario",
        view_factory_id="inventory.overview_view", required_permission="INVENTORY.ver",
    ))
    registry.register(RouteDefinition(
        route_id="whatsapp.status", module_id="whatsapp", title="WhatsApp",
        view_factory_id="whatsapp.status_view", feature_flag="whatsapp_module",
    ))
    return registry
