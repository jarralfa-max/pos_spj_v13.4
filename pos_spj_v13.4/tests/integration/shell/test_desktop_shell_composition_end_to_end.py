"""SHELL-16½ capstone — pieces 4a (`desktop_shell_window_composition.py`)
and 4b (`desktop_shell_authentication_composition.py`) proven TOGETHER as
one real chain: a real login, through the real `AuthenticationCoordinator`,
building a real `ApplicationContext`, wrapped in a real
`LegacySessionAdapter`, handed to a real `build_application_window()`,
producing a real, navigable `ApplicationWindow` — the first time in this
codebase's history this full path has ever run end-to-end, standing in
for what `main.py`'s eventual replacement will do.

Still deliberately NOT `main.py` itself, and still not wired there — that
cutover is separate, higher-blast-radius work requiring its own explicit
sign-off, matching the scope boundary every SHELL-16 module migration
already drew for itself.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402

from backend.bootstrap.composition_root import CompositionRoot  # noqa: E402
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter  # noqa: E402
from backend.bootstrap.wiring.security_wiring import SecurityModuleProvider  # noqa: E402
from backend.bootstrap.wiring.shared_wiring import SharedModuleProvider  # noqa: E402
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema  # noqa: E402
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema  # noqa: E402
from backend.security.credentials.password_hasher import BcryptPasswordHasher  # noqa: E402
from backend.security.credentials.password_policy import PasswordPolicy  # noqa: E402
from backend.security.provisioning.installation_repository import SqliteInstallationRepository  # noqa: E402
from backend.security.provisioning.provision_installation_use_case import (  # noqa: E402
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository  # noqa: E402
from frontend.desktop.auth.login_window import LoginWindow  # noqa: E402
from frontend.desktop.modules.transfers.shell_registration import TRANSFERS_ROUTE_ID  # noqa: E402
from frontend.desktop.modules.transfers.transfers_view import TransfersView  # noqa: E402
from frontend.desktop.shell.application_shell.application_window import ApplicationWindow  # noqa: E402
from frontend.desktop.shell.desktop_shell_authentication_composition import (  # noqa: E402
    build_authentication_coordinator,
)
from frontend.desktop.shell.desktop_shell_window_composition import build_application_window  # noqa: E402
from tests.integration._born_clean_db import make_db  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
PASSWORD = "Correct-Horse-9!"
OWNER_USERNAME = "jarralfa"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def container(tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(tmp_path / "app_data"))
    return CompositionRoot([SharedModuleProvider(), SecurityModuleProvider()]).build()


@pytest.fixture
def provisioned_conn():
    conn = make_db()
    ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(
        company_name="Carnicería SPJ", branch_name="Sucursal Centro", owner_username=OWNER_USERNAME,
        owner_password=PASSWORD, owner_full_name="Jose Alfaro", now=T0,
    )
    # The 9 migrated modules' own schemas aren't part of the auth/bootstrap
    # schema make_db() seeds — add just enough for the module this test
    # navigates into (transfers), same lightweight fixture its own SHELL-16
    # tests already use. The provisioned branch becomes the active branch
    # via ApplicationContextBuilder reading `sucursales`, so it must exist
    # there before transfers' own schema references it.
    create_transfers_schema(conn)
    create_procurement_schema(conn)
    conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    conn.commit()
    return conn


def _autofill_and_accept(login_window: LoginWindow) -> int:
    login_window._username_input.setText(OWNER_USERNAME)
    login_window._password_input.setText(PASSWORD)
    login_window._on_login()
    return QDialog.Accepted if login_window.authentication_result is not None else QDialog.Rejected


def test_login_builds_a_real_navigable_application_window(app, provisioned_conn, container, monkeypatch):
    monkeypatch.setattr(LoginWindow, "exec_", _autofill_and_accept)

    windows: list[ApplicationWindow] = []

    def on_authenticated(context):
        window = build_application_window(
            context=context, connection=provisioned_conn,
            session_context=LegacySessionAdapter(context),
            health_report=_healthy_report(),
        )
        windows.append(window)

    coordinator = build_authentication_coordinator(
        connection=provisioned_conn, container=container, on_authenticated=on_authenticated,
        workstation_id="ws-1",
    )
    ran = coordinator.run()

    assert ran is True
    assert len(windows) == 1
    window = windows[0]
    assert isinstance(window, ApplicationWindow)

    # The owner role must carry admin-level access — PermissionEvaluator's
    # is_admin() bypass — so every migrated module's sidebar item resolves.
    assert window.sidebar.visible_item_count == 9

    result = window.navigate(TRANSFERS_ROUTE_ID)
    assert isinstance(result.view, TransfersView)


def _healthy_report():
    from backend.bootstrap.health.health_status import HealthReport, HealthStatus

    return HealthReport(overall_status=HealthStatus.HEALTHY, checks=(), generated_at=datetime.now(timezone.utc))
