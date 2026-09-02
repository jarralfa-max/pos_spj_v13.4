"""InitialSetupWizard — SHELL-2 UI tests.

Runs headless (offscreen Qt), against a real in-memory born-clean DB via
`tests.integration._born_clean_db.make_db()` — this drives the wizard
through its actual `ProvisioningPresenter` → `ProvisionInstallationUseCase`
wiring, not a mock, so a broken page↔use-case contract fails here.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.security.credentials.password_hasher import BcryptPasswordHasher  # noqa: E402
from backend.security.credentials.password_policy import PasswordPolicy  # noqa: E402
from backend.security.provisioning.installation_repository import (  # noqa: E402
    SqliteInstallationRepository,
)
from backend.security.provisioning.provision_installation_use_case import (  # noqa: E402
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import (  # noqa: E402
    SqliteRecoveryCodeRepository,
)
from frontend.desktop.provisioning.initial_setup_wizard import InitialSetupWizard  # noqa: E402
from frontend.desktop.provisioning.provisioning_presenter import ProvisioningPresenter  # noqa: E402
from tests.integration._born_clean_db import make_db  # noqa: E402

WELCOME, COMPANY, BRANCH, WORKSTATION, OWNER, RECOVERY, CONFIRMATION = range(7)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def wizard(app):
    conn = make_db()
    use_case = ProvisionInstallationUseCase(
        conn,
        installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(),
        password_policy=PasswordPolicy(),
    )
    return InitialSetupWizard(presenter=ProvisioningPresenter(use_case))


def _fill_company(wizard, name="Carnicería SPJ", rfc="SPJ010101AAA"):
    wizard._pages[COMPANY].company_name.setText(name)
    wizard._pages[COMPANY].company_rfc.setText(rfc)


def _fill_branch(wizard, name="Sucursal Centro"):
    wizard._pages[BRANCH].branch_name.setText(name)


def _fill_workstation(wizard, name="Caja 1"):
    wizard._pages[WORKSTATION].workstation_name.setText(name)


def _fill_owner(wizard, *, username="jarralfa", password="Correct-Horse-9!"):
    wizard._pages[OWNER].full_name.setText("Jose Alfaro")
    wizard._pages[OWNER].username.setText(username)
    wizard._pages[OWNER].password.setText(password)
    wizard._pages[OWNER].password_confirm.setText(password)


def _fill_recovery(wizard, email="jarr.alfa@gmail.com"):
    wizard._pages[RECOVERY].recovery_contact.setText(email)


def _complete_happy_path(wizard):
    wizard._go_next()  # welcome -> company
    _fill_company(wizard)
    wizard._go_next()  # -> branch
    _fill_branch(wizard)
    wizard._go_next()  # -> workstation
    _fill_workstation(wizard)
    wizard._go_next()  # -> owner
    _fill_owner(wizard)
    wizard._go_next()  # -> recovery
    _fill_recovery(wizard)
    wizard._go_next()  # -> confirmation (review)
    wizard._go_next()  # Finalizar


def test_wizard_has_seven_pages(wizard):
    assert len(wizard._pages) == 7


def test_starts_on_welcome_page_with_next_button(wizard):
    assert wizard._current_index == WELCOME
    assert wizard._next_btn.text() == "Siguiente"


def test_empty_required_field_blocks_navigation(wizard):
    wizard._go_next()  # -> company
    wizard._go_next()  # company_name left empty
    assert wizard._current_index == COMPANY
    assert "obligatorio" in wizard._error_label.text()


def test_filling_required_field_allows_navigation(wizard):
    wizard._go_next()
    _fill_company(wizard)
    wizard._go_next()
    assert wizard._current_index == BRANCH


def test_password_mismatch_blocks_navigation(wizard):
    wizard._go_next()
    _fill_company(wizard)
    wizard._go_next()
    _fill_branch(wizard)
    wizard._go_next()
    _fill_workstation(wizard)
    wizard._go_next()

    wizard._pages[OWNER].full_name.setText("Jose Alfaro")
    wizard._pages[OWNER].username.setText("jarralfa")
    wizard._pages[OWNER].password.setText("Correct-Horse-9!")
    wizard._pages[OWNER].password_confirm.setText("Different-9!")
    wizard._go_next()

    assert wizard._current_index == OWNER
    assert "no coinciden" in wizard._error_label.text()


def test_weak_password_blocks_navigation(wizard):
    wizard._go_next()
    _fill_company(wizard)
    wizard._go_next()
    _fill_branch(wizard)
    wizard._go_next()
    _fill_workstation(wizard)
    wizard._go_next()

    _fill_owner(wizard, password="weak")
    wizard._go_next()

    assert wizard._current_index == OWNER
    assert "caracteres" in wizard._error_label.text()


def test_invalid_recovery_email_blocks_navigation(wizard):
    wizard._go_next()  # welcome -> company
    _fill_company(wizard)
    wizard._go_next()
    _fill_branch(wizard)
    wizard._go_next()
    _fill_workstation(wizard)
    wizard._go_next()
    _fill_owner(wizard)
    wizard._go_next()

    wizard._pages[RECOVERY].recovery_contact.setText("not-an-email")
    wizard._go_next()

    assert wizard._current_index == RECOVERY
    assert "correo" in wizard._error_label.text().lower()


def test_back_navigation_preserves_entered_values(wizard):
    wizard._go_next()
    _fill_company(wizard, name="Carnicería SPJ")
    wizard._go_next()
    wizard._go_back()
    assert wizard._pages[COMPANY].company_name.value() == "Carnicería SPJ"


def test_back_button_disabled_on_first_page(wizard):
    assert wizard._back_btn.isEnabled() is False


def test_confirmation_page_shows_summary_before_finish(wizard):
    wizard._go_next()
    _fill_company(wizard)
    wizard._go_next()
    _fill_branch(wizard)
    wizard._go_next()
    _fill_workstation(wizard)
    wizard._go_next()
    _fill_owner(wizard)
    wizard._go_next()
    _fill_recovery(wizard)
    wizard._go_next()

    assert wizard._current_index == CONFIRMATION
    assert wizard._next_btn.text() == "Finalizar"
    assert "jarralfa" in wizard._confirmation_page._summary_owner.text()


def test_happy_path_provisions_and_shows_recovery_codes(wizard):
    _complete_happy_path(wizard)

    assert wizard._provisioned is True
    assert wizard._next_btn.text() == "Cerrar"
    result = wizard.provisioning_result()
    assert result is not None
    assert len(result.recovery_codes) == 10


def test_owner_account_can_log_in_after_wizard_completes(wizard):
    _complete_happy_path(wizard)

    from core.services.audit_service import AuditService
    from core.services.auth_service import AuthService
    from core.services.security_service import SecurityService
    from repositories.audit_repository import AuditRepository
    from repositories.auth_repository import AuthRepository
    from repositories.security_repository import SecurityRepository

    conn = wizard._presenter._use_case._conn
    auth_service = AuthService(
        auth_repo=AuthRepository(conn),
        security_service=SecurityService(SecurityRepository(conn)),
        audit_service=AuditService(AuditRepository(conn)),
    )
    logged_in = auth_service.authenticate("jarralfa", "Correct-Horse-9!")
    assert logged_in["rol"] == "system_owner"


def test_cannot_close_before_acknowledging_recovery_codes(wizard):
    from PyQt5.QtGui import QCloseEvent

    _complete_happy_path(wizard)

    event = QCloseEvent()
    wizard.closeEvent(event)
    assert event.isAccepted() is False


def test_can_close_after_acknowledging_recovery_codes(wizard):
    from PyQt5.QtGui import QCloseEvent

    _complete_happy_path(wizard)
    wizard._confirmation_page._acknowledge.setChecked(True)

    event = QCloseEvent()
    wizard.closeEvent(event)
    assert event.isAccepted() is True


def test_close_button_disabled_until_acknowledged(wizard):
    _complete_happy_path(wizard)
    assert wizard._next_btn.isEnabled() is False
    wizard._confirmation_page._acknowledge.setChecked(True)
    assert wizard._next_btn.isEnabled() is True


def test_cancel_is_hidden_after_provisioning(wizard):
    _complete_happy_path(wizard)
    assert wizard._cancel_btn.isVisible() is False


def test_duplicate_username_shows_error_without_crashing(wizard):
    _complete_happy_path(wizard)

    conn = wizard._presenter._use_case._conn
    from backend.security.provisioning.provision_installation_use_case import (
        ProvisionInstallationUseCase,
    )

    second_use_case = ProvisionInstallationUseCase(
        conn,
        installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(),
        password_policy=PasswordPolicy(),
    )
    second_wizard = InitialSetupWizard(presenter=ProvisioningPresenter(second_use_case))
    _complete_happy_path(second_wizard)

    # Second attempt on an already-provisioned installation must surface a
    # Spanish error, not raise past the UI layer.
    assert second_wizard._provisioned is False
    assert second_wizard._error_label.isVisible() or second_wizard._error_label.text()
