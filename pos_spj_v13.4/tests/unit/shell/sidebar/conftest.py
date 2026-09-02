from datetime import datetime, timezone

import pytest

from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.health.health_status import HealthCheckResult, HealthReport, HealthStatus
from frontend.desktop.shell.modules.health_requirement import HealthRequirement
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry


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


def healthy_report(*check_names: str) -> HealthReport:
    checks = tuple(HealthCheckResult(name, HealthStatus.HEALTHY) for name in check_names)
    return HealthReport(overall_status=HealthStatus.HEALTHY, checks=checks, generated_at=datetime.now(timezone.utc))


@pytest.fixture
def context() -> ApplicationContext:
    return make_context()


@pytest.fixture
def modules() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(ModuleDescriptor(module_id="sales", display_name="Ventas"))
    registry.register(ModuleDescriptor(
        module_id="inventory", display_name="Inventario",
        health_requirements=(HealthRequirement(check_name="database"),),
    ))
    return registry


@pytest.fixture
def routes() -> RouteRegistry:
    registry = RouteRegistry()
    registry.register(RouteDefinition(
        route_id="sales.pos", module_id="sales", title="POS", view_factory_id="v1",
    ))
    registry.register(RouteDefinition(
        route_id="inventory.overview", module_id="inventory", title="Inventario", view_factory_id="v2",
    ))
    return registry
