import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.security.credentials.password_hasher import BcryptPasswordHasher  # noqa: E402
from backend.security.credentials.password_policy import PasswordPolicy  # noqa: E402
from backend.security.provisioning.installation_repository import SqliteInstallationRepository  # noqa: E402
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
from frontend.desktop.auth.account_recovery_dialog import AccountRecoveryDialog  # noqa: E402
from tests.integration._born_clean_db import make_db  # noqa: E402

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def dialog(app):
    conn = make_db()
    provision_uc = ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    provision_uc.execute(
        company_name="SPJ", branch_name="Centro", owner_username="jarralfa",
        owner_password="Correct-Horse-9!", owner_full_name="Jose Alfaro", now=T0,
    )
    conn.commit()

    recovery_service = AccountRecoveryService(
        token_repository=SqliteRecoveryTokenRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    )
    return AccountRecoveryDialog(
        begin_use_case=BeginAccountRecoveryUseCase(recovery_service),
        complete_use_case=CompleteAccountRecoveryUseCase(recovery_service),
    )


def test_starts_on_request_step(dialog):
    assert dialog._stack.currentIndex() == 0


def test_empty_username_shows_error(dialog):
    dialog._username_input.setText("")
    dialog._on_request_token()
    assert dialog._error_label.text() != ""
    assert dialog._stack.currentIndex() == 0


def test_requesting_token_advances_to_reset_step(dialog):
    dialog._username_input.setText("jarralfa")
    dialog._on_request_token()
    assert dialog._stack.currentIndex() == 1
    assert dialog._token_display.text() == dialog._raw_token
    assert len(dialog._raw_token) >= 32


def test_password_mismatch_blocks_reset(dialog):
    dialog._username_input.setText("jarralfa")
    dialog._on_request_token()
    dialog._new_password.setText("Correct-Horse-9!")
    dialog._confirm_password.setText("Different-9!")
    dialog._on_reset_password()
    assert dialog._error_label.text() != ""
    assert dialog.result() != dialog.Accepted


def test_weak_password_blocks_reset(dialog):
    dialog._username_input.setText("jarralfa")
    dialog._on_request_token()
    dialog._new_password.setText("weak")
    dialog._confirm_password.setText("weak")
    dialog._on_reset_password()
    assert dialog._error_label.text() != ""


def test_successful_reset_accepts_the_dialog(dialog):
    dialog._username_input.setText("jarralfa")
    dialog._on_request_token()
    dialog._new_password.setText("Brand-New-Pass-9!")
    dialog._confirm_password.setText("Brand-New-Pass-9!")
    dialog._on_reset_password()
    assert dialog.result() == dialog.Accepted


def test_used_token_cannot_be_reused(dialog):
    dialog._username_input.setText("jarralfa")
    dialog._on_request_token()
    dialog._new_password.setText("Brand-New-Pass-9!")
    dialog._confirm_password.setText("Brand-New-Pass-9!")
    dialog._on_reset_password()
    assert dialog.result() == dialog.Accepted

    # attempt to reuse the same already-consumed token
    dialog._error_label.setText("")
    dialog._on_reset_password()
    assert dialog._error_label.text() != ""
