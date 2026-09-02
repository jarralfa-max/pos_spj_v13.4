"""LoginWindow — SHELL-7 UI tests.

Headless (offscreen Qt), against a real provisioned in-memory DB via the
actual SHELL-2/SHELL-7 use cases — not mocks.
"""
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.security.authentication.authentication_attempt_repository import (  # noqa: E402
    SqliteAuthenticationAttemptRepository,
)
from backend.security.authentication.authenticate_user_use_case import AuthenticateUserUseCase  # noqa: E402
from backend.security.authentication.user_credentials import SqliteUserCredentialsRepository  # noqa: E402
from backend.security.credentials.password_hasher import (  # noqa: E402
    Argon2idPasswordHasher,
    BcryptPasswordHasher,
)
from backend.security.credentials.password_policy import PasswordPolicy  # noqa: E402
from backend.security.credentials.password_verification import MultiSchemePasswordVerifier  # noqa: E402
from backend.security.provisioning.installation_repository import SqliteInstallationRepository  # noqa: E402
from backend.security.provisioning.installation_summary_query import (  # noqa: E402
    InstallationSummaryQueryService,
)
from backend.security.provisioning.provision_installation_use_case import (  # noqa: E402
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository  # noqa: E402
from backend.security.recovery.account_recovery_service import AccountRecoveryService  # noqa: E402
from backend.security.recovery.begin_account_recovery_use_case import BeginAccountRecoveryUseCase  # noqa: E402
from backend.security.recovery.complete_account_recovery_use_case import (  # noqa: E402
    CompleteAccountRecoveryUseCase,
)
from backend.security.recovery.recovery_token_repository import SqliteRecoveryTokenRepository  # noqa: E402
from backend.security.sessions.account_lockout_policy import AccountLockoutPolicy  # noqa: E402
from backend.security.sessions.session_manager import SessionManager  # noqa: E402
from backend.security.sessions.session_repository import InMemorySessionRepository  # noqa: E402
from frontend.desktop.auth.login_window import LoginWindow  # noqa: E402
from tests.integration._born_clean_db import make_db  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
PASSWORD = "Correct-Horse-9!"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def services(app):
    conn = make_db()
    provision_uc = ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    provision_uc.execute(
        company_name="Carnicería SPJ", branch_name="Sucursal Centro", owner_username="jarralfa",
        owner_password=PASSWORD, owner_full_name="Jose Alfaro", now=T0,
    )
    conn.commit()

    auth_uc = AuthenticateUserUseCase(
        credentials_repository=SqliteUserCredentialsRepository(conn),
        attempt_repository=SqliteAuthenticationAttemptRepository(conn),
        password_verifier=MultiSchemePasswordVerifier(
            primary=Argon2idPasswordHasher(), legacy=(BcryptPasswordHasher(),),
        ),
        lockout_policy=AccountLockoutPolicy(failed_attempt_limit=3),
        session_manager=SessionManager(session_repository=InMemorySessionRepository()),
    )
    recovery_service = AccountRecoveryService(
        token_repository=SqliteRecoveryTokenRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    return {
        "conn": conn,
        "authenticate": auth_uc,
        "begin_recovery": BeginAccountRecoveryUseCase(recovery_service),
        "complete_recovery": CompleteAccountRecoveryUseCase(recovery_service),
        "summary": InstallationSummaryQueryService(conn),
    }


def _window(services, **overrides):
    kwargs = dict(
        authenticate_use_case=services["authenticate"],
        begin_recovery_use_case=services["begin_recovery"],
        complete_recovery_use_case=services["complete_recovery"],
        installation_summary_query=services["summary"],
        workstation_id="ws-1",
    )
    kwargs.update(overrides)
    return LoginWindow(**kwargs)


def test_header_shows_company_and_branch_name(services):
    win = _window(services)
    # index 0 is StandardDialog's own title QLabel; the PageHeader LoginWindow
    # adds is the next widget in content_layout().
    header = win.content_layout().itemAt(1).widget()
    assert "Carnicería SPJ" in header._subtitle.text()
    assert "Sucursal Centro" in header._subtitle.text()


def test_empty_fields_show_error_without_calling_use_case(services):
    win = _window(services)
    win._on_login()
    assert win._error_label.isVisible() or win._error_label.text()
    assert win.authentication_result is None


def test_successful_login_sets_authentication_result(services):
    win = _window(services)
    win._username_input.setText("jarralfa")
    win._password_input.setText(PASSWORD)
    win._on_login()
    assert win.authentication_result is not None
    assert win.authentication_result.credentials.username == "jarralfa"


def test_wrong_password_shows_generic_error_and_clears_password_field(services):
    win = _window(services)
    win._username_input.setText("jarralfa")
    win._password_input.setText("wrong-password")
    win._on_login()
    assert win.authentication_result is None
    assert win._error_label.text() != ""
    assert win._password_input.value() == ""


def test_lockout_message_shown_after_repeated_failures(services):
    win = _window(services)
    for _ in range(3):
        win._username_input.setText("jarralfa")
        win._password_input.setText("wrong-password")
        win._on_login()
        services["conn"].commit()

    win._username_input.setText("jarralfa")
    win._password_input.setText(PASSWORD)
    win._on_login()
    assert "bloqueada" in win._error_label.text().lower()
    assert win.authentication_result is None


def test_login_button_re_enabled_after_attempt(services):
    win = _window(services)
    win._username_input.setText("jarralfa")
    win._password_input.setText("wrong-password")
    win._on_login()
    assert win._login_btn.isEnabled() is True
    assert win._login_btn.text() == "Iniciar sesión"


def test_forgot_password_button_exists(services):
    win = _window(services)
    assert hasattr(win, "_on_forgot_password")
