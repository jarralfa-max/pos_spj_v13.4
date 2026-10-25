"""Install profile = hidden AND blocked (backend + router), and a database
newer than the binary never starts silently."""
from __future__ import annotations

import sqlite3

import pytest

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapSeverity
from backend.bootstrap.permission_evaluator import PermissionEvaluator
from backend.bootstrap.steps.schema_compatibility_step import SchemaCompatibilityStep
from backend.domain.software_distribution.install_profile import (
    EnabledCapabilities,
    InstallProfile,
)
from frontend.desktop.shell.router.desktop_router import DesktopRouter
from frontend.desktop.shell.router.errors import NavigationFeatureDisabledError
from frontend.desktop.shell.routing.route_definition import RouteDefinition
from frontend.desktop.shell.routing.route_registry import RouteRegistry
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry
from tests.unit.shell.router.conftest import make_context

ESSENTIAL = EnabledCapabilities.resolve(InstallProfile.POS_ESSENTIAL)


def test_not_installed_module_is_denied_even_to_the_administrator():
    admin = make_context(roles=("admin",), permissions=frozenset({"*"}), capabilities=ESSENTIAL)
    evaluator = PermissionEvaluator(admin)
    assert evaluator.has_permission("POS.ver")
    assert not evaluator.has_permission("RRHH.nomina.generar")
    assert not evaluator.has_permission("FINANZAS.ver")
    assert not evaluator.has_permission("MERMA.ver")  # auditoría de permisos 968e0bc: Mermas es `MERMA.<accion>`
    cashier = make_context(permissions=frozenset({"RRHH.*", "POS.VER"}), capabilities=ESSENTIAL)
    assert not PermissionEvaluator(cashier).has_permission("RRHH.ver")
    full = make_context(roles=("admin",), permissions=frozenset())
    assert PermissionEvaluator(full).has_permission("RRHH.ver")  # default: everything


def test_router_refuses_a_module_outside_the_profile():
    routes = RouteRegistry()
    routes.register(RouteDefinition(route_id="hr.home", module_id="hr", title="RR. HH.",
                                    view_factory_id="hr.view"))
    routes.register(RouteDefinition(route_id="pos.home", module_id="sales_pos", title="POS",
                                    view_factory_id="pos.view"))
    views = ViewFactoryRegistry()
    views.register("hr.view", lambda: "hr")
    views.register("pos.view", lambda: "pos")
    router = DesktopRouter(route_registry=routes, view_factory_registry=views,
                           initial_context=make_context(capabilities=ESSENTIAL))
    assert router.navigate("pos.home").view == "pos"
    with pytest.raises(NavigationFeatureDisabledError, match="perfil de instalación"):
        router.navigate("hr.home")


def test_branch_change_keeps_the_station_profile():
    from backend.bootstrap.application_context import FeatureContext

    context = make_context(capabilities=ESSENTIAL)
    moved = context.with_branch(branch_id="b2", branch_name="Norte", permissions=frozenset(),
                                feature_context=FeatureContext())
    assert moved.capabilities is ESSENTIAL


def _context_with(tmp_path, versions):
    connection = sqlite3.connect(str(tmp_path / "db.sqlite"))
    connection.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY)")
    connection.executemany("INSERT INTO schema_migrations VALUES (?)", [(v,) for v in versions])
    connection.commit()
    context = BootstrapContext(db_path=tmp_path / "db.sqlite")
    context.conn = connection
    return context


def test_database_from_a_newer_release_stops_the_start(tmp_path):
    result = SchemaCompatibilityStep().run(_context_with(tmp_path, ["000", "337", "999"]))
    assert result.severity is BootstrapSeverity.FATAL
    assert "999" in result.message and "respaldo" in result.message


def test_known_or_fresh_schema_passes(tmp_path):
    assert SchemaCompatibilityStep().run(_context_with(tmp_path, ["000", "337"])).severity \
        is BootstrapSeverity.INFO
    fresh = BootstrapContext(db_path=tmp_path / "fresh.sqlite")
    fresh.conn = sqlite3.connect(str(tmp_path / "fresh.sqlite"))
    assert SchemaCompatibilityStep().run(fresh).severity is BootstrapSeverity.INFO
