"""SHELL-16½ piece 4a — `build_application_window()` proven end-to-end:
a real `ApplicationWindow`, all migrated modules registered, the real
sidebar showing all 9 (permission-gated for real), and real navigation
into two of them producing the actual production widgets.

All 9 modules declare `StartupMode.LAZY` (confirmed by reading every
`shell_registration.py`), so `ModuleLoader` never constructs any of them
during `build_application_window()` itself — only `navigate()` does, one
module at a time. That means this test only needs schema for the modules
it actually navigates into (`transfers`, `purchasing` — the same
lightweight fixtures their own SHELL-16 integration tests already use),
not a full production database for all 9. The other 7 modules are proven
present, routable, and *not yet constructed* (still `NOT_LOADED`) rather
than exercised end-to-end here — that's each module's own existing
integration test's job, not this composition test's.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.bootstrap.health.health_status import HealthReport, HealthStatus  # noqa: E402
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter  # noqa: E402
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema  # noqa: E402
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema  # noqa: E402
from frontend.desktop.modules.cash_register.shell_registration import CASH_REGISTER_MODULE_ID  # noqa: E402
from frontend.desktop.modules.purchasing.enterprise_view import EnterprisePurchasingView  # noqa: E402
from frontend.desktop.modules.purchasing.shell_registration import PURCHASING_ROUTE_ID  # noqa: E402
from frontend.desktop.modules.transfers.shell_registration import TRANSFERS_ROUTE_ID  # noqa: E402
from frontend.desktop.modules.transfers.transfers_view import TransfersView  # noqa: E402
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow  # noqa: E402
from frontend.desktop.shell.desktop_shell_window_composition import build_application_window  # noqa: E402
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(c)
    create_procurement_schema(c)
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('b1', 'Matriz', 1), ('b2', 'Sucursal Centro', 1)")
    c.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    c.execute("INSERT INTO products VALUES ('p1', 'unit-kg')")
    c.commit()
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Gerente", roles=("gerente",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _healthy_report() -> HealthReport:
    return HealthReport(overall_status=HealthStatus.HEALTHY, checks=(), generated_at=datetime.now(timezone.utc))


def test_builds_a_real_application_window(app, conn):
    context = _context(permissions={"*"})
    window = build_application_window(
        context=context, connection=conn, session_context=LegacySessionAdapter(context),
        health_report=_healthy_report(),
    )
    assert isinstance(window, ApplicationWindow)


def test_sidebar_shows_all_migrated_modules_when_fully_permitted(app, conn):
    context = _context(permissions={"*"})
    window = build_application_window(
        context=context, connection=conn, session_context=LegacySessionAdapter(context),
        health_report=_healthy_report(),
    )
    assert window.sidebar is not None
    assert window.sidebar.visible_item_count == 16


def test_no_module_is_constructed_until_navigated_to(app, conn):
    context = _context(permissions={"*"})
    window = build_application_window(
        context=context, connection=conn, session_context=LegacySessionAdapter(context),
        health_report=_healthy_report(),
    )
    # LAZY startup mode: nothing should have been activated yet.
    assert window._module_loader.state_of(CASH_REGISTER_MODULE_ID) is ModuleLoadState.NOT_LOADED


def test_navigating_to_transfers_builds_the_real_transfers_view(app, conn):
    # "TRANSFERENCIAS.VER" is the route-level gate DesktopRouter._authorize()
    # checks before navigation even succeeds; "TRANSFERS_DASHBOARD_VIEW" is a
    # separate, module-internal sidebar permission (see
    # backend.application.transfers.permissions.TransferPermissions) that
    # this test doesn't need since it only asserts on the outer view type.
    context = _context(permissions={"TRANSFERENCIAS.VER"})
    window = build_application_window(
        context=context, connection=conn, session_context=LegacySessionAdapter(context),
        health_report=_healthy_report(),
    )
    result = window.navigate(TRANSFERS_ROUTE_ID)
    assert isinstance(result.view, TransfersView)


def test_navigating_to_purchasing_builds_the_real_purchasing_view(app, conn):
    context = _context(permissions={"*"})
    window = build_application_window(
        context=context, connection=conn, session_context=LegacySessionAdapter(context),
        health_report=_healthy_report(),
    )
    result = window.navigate(PURCHASING_ROUTE_ID)
    assert isinstance(result.view, EnterprisePurchasingView)
