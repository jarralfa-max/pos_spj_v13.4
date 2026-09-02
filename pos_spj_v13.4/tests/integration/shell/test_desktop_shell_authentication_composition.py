"""SHELL-16½ piece 4b — `build_authentication_coordinator()` proven
against a real, provisioned SQLite database: every factory it wires
(`setup_wizard_factory`, `login_window_factory`,
`build_application_context`, the locked/recovery dialog factories)
produces the real production object, and one true end-to-end run drives
`AuthenticationCoordinator.run()` through a real login all the way to
`on_authenticated` receiving a real `ApplicationContext`.

`LoginWindow.exec_()` normally blocks on a real Qt modal loop — there is
no human here to click it. `_autofill_and_accept()` monkeypatches
`LoginWindow.exec_` for the run itself to do exactly what a person would
(fill the real fields, click login) and return the same `QDialog.Accepted`
/`Rejected` code `exec_()` would — the same technique
`tests/ui/test_login_window.py` already uses to test `LoginWindow` itself
(`win._on_login()` called directly, no `exec_()` at all), just applied one
layer up so `AuthenticationCoordinator.run()`'s own call to `exec_()` is
what's exercised, not bypassed.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication, QDialog  # noqa: E402

from backend.bootstrap.composition_root import CompositionRoot  # noqa: E402
from backend.bootstrap.wiring.security_wiring import SecurityModuleProvider  # noqa: E402
from backend.bootstrap.wiring.shared_wiring import SharedModuleProvider  # noqa: E402
from backend.security.credentials.password_hasher import BcryptPasswordHasher  # noqa: E402
from backend.security.credentials.password_policy import PasswordPolicy  # noqa: E402
from backend.security.provisioning.installation_repository import SqliteInstallationRepository  # noqa: E402
from backend.security.provisioning.provision_installation_use_case import (  # noqa: E402
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository  # noqa: E402
from frontend.desktop.auth.authentication_coordinator import AuthenticationCoordinator  # noqa: E402
from frontend.desktop.auth.installation_status_dialogs import (  # noqa: E402
    InstallationLockedDialog,
    InstallationRecoveryRequiredDialog,
)
from frontend.desktop.auth.login_window import LoginWindow  # noqa: E402
from frontend.desktop.provisioning.initial_setup_wizard import InitialSetupWizard  # noqa: E402
from frontend.desktop.shell.desktop_shell_authentication_composition import (  # noqa: E402
    build_authentication_coordinator,
)
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
    root = CompositionRoot([SharedModuleProvider(), SecurityModuleProvider()])
    return root.build()


@pytest.fixture
def unprovisioned_conn():
    return make_db()


@pytest.fixture
def provisioned_conn(unprovisioned_conn):
    conn = unprovisioned_conn
    ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(
        company_name="Carnicería SPJ", branch_name="Sucursal Centro", owner_username=OWNER_USERNAME,
        owner_password=PASSWORD, owner_full_name="Jose Alfaro", now=T0,
    )
    conn.commit()
    return conn


def test_returns_a_real_authentication_coordinator(app, provisioned_conn, container):
    coordinator = build_authentication_coordinator(
        connection=provisioned_conn, container=container, on_authenticated=lambda _ctx: None,
    )
    assert isinstance(coordinator, AuthenticationCoordinator)


def test_setup_wizard_factory_builds_a_real_wizard_against_the_unprovisioned_db(app, unprovisioned_conn, container):
    coordinator = build_authentication_coordinator(
        connection=unprovisioned_conn, container=container, on_authenticated=lambda _ctx: None,
    )
    wizard = coordinator._setup_wizard_factory()
    assert isinstance(wizard, InitialSetupWizard)


def test_login_window_factory_builds_a_real_window_that_authenticates_for_real(app, provisioned_conn, container):
    coordinator = build_authentication_coordinator(
        connection=provisioned_conn, container=container, on_authenticated=lambda _ctx: None,
    )
    login_window = coordinator._login_window_factory()
    assert isinstance(login_window, LoginWindow)

    login_window._username_input.setText(OWNER_USERNAME)
    login_window._password_input.setText(PASSWORD)
    login_window._on_login()
    assert login_window.authentication_result is not None
    assert login_window.authentication_result.credentials.username == OWNER_USERNAME


def test_dialog_factories_build_the_real_dialogs(app, provisioned_conn, container):
    coordinator = build_authentication_coordinator(
        connection=provisioned_conn, container=container, on_authenticated=lambda _ctx: None,
    )
    assert isinstance(coordinator._locked_dialog_factory(), InstallationLockedDialog)
    assert isinstance(coordinator._recovery_required_dialog_factory(), InstallationRecoveryRequiredDialog)


def _autofill_and_accept(login_window: LoginWindow) -> int:
    login_window._username_input.setText(OWNER_USERNAME)
    login_window._password_input.setText(PASSWORD)
    login_window._on_login()
    return QDialog.Accepted if login_window.authentication_result is not None else QDialog.Rejected


def test_full_run_reaches_on_authenticated_with_a_real_application_context(
    app, provisioned_conn, container, monkeypatch,
):
    monkeypatch.setattr(LoginWindow, "exec_", _autofill_and_accept)

    captured = {}
    coordinator = build_authentication_coordinator(
        connection=provisioned_conn, container=container,
        on_authenticated=lambda context: captured.setdefault("context", context),
        workstation_id="ws-1",
    )
    ran = coordinator.run()

    assert ran is True
    assert "context" in captured
    context = captured["context"]
    assert context.user_name == "Jose Alfaro"
    assert context.branch_name == "Sucursal Centro"
    assert context.workstation_id == "ws-1"
    assert len(context.permissions) > 0


def test_wrong_password_does_not_reach_on_authenticated(app, provisioned_conn, container, monkeypatch):
    def _wrong_password_reject(login_window: LoginWindow) -> int:
        login_window._username_input.setText(OWNER_USERNAME)
        login_window._password_input.setText("not-the-password")
        login_window._on_login()
        return QDialog.Accepted if login_window.authentication_result is not None else QDialog.Rejected

    monkeypatch.setattr(LoginWindow, "exec_", _wrong_password_reject)

    captured = {}
    coordinator = build_authentication_coordinator(
        connection=provisioned_conn, container=container,
        on_authenticated=lambda context: captured.setdefault("context", context),
    )
    ran = coordinator.run()

    assert ran is False
    assert "context" not in captured
