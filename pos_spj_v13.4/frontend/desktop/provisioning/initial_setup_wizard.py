"""InitialSetupWizard — SHELL-2.

Shown instead of the normal login window whenever
`InstallationStatusQuery.requires_setup_wizard()` is True (wiring that
gate in is SHELL-7/AuthenticationCoordinator's job — this dialog is
self-contained and testable on its own). Seven pages in a `QStackedWidget`,
Back/Siguiente/Cancelar footer that becomes Finalizar on the last page and
Cerrar after a successful `ProvisioningPresenter.finish()`.

The dialog never touches the database or `PasswordHasher` directly — all of
that goes through `ProvisioningPresenter`, injected in.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from backend.security.credentials.errors import PasswordPolicyViolationError
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.create_initial_owner_use_case import OwnerUsernameTakenError
from backend.security.provisioning.errors import (
    InstallationAlreadyProvisionedError,
    InstallationLockedError,
)
from backend.security.provisioning.provision_installation_use_case import ProvisioningResult
from frontend.desktop.components.buttons import (
    create_ghost_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.provisioning.pages.branch_page import BranchPage
from frontend.desktop.provisioning.pages.company_page import CompanyPage
from frontend.desktop.provisioning.pages.confirmation_page import ConfirmationPage
from frontend.desktop.provisioning.pages.owner_account_page import OwnerAccountPage
from frontend.desktop.provisioning.pages.security_recovery_page import SecurityRecoveryPage
from frontend.desktop.provisioning.pages.welcome_page import WelcomePage
from frontend.desktop.provisioning.pages.workstation_page import WorkstationPage
from frontend.desktop.provisioning.provisioning_presenter import ProvisioningPresenter
from frontend.desktop.provisioning.provisioning_view_model import ProvisioningViewModel
from frontend.desktop.themes.tokens import DialogMetrics, Spacing


class InitialSetupWizard(StandardDialog):
    def __init__(
        self, parent=None, *, presenter: ProvisioningPresenter,
        password_policy: PasswordPolicy | None = None,
    ) -> None:
        super().__init__(parent, title="Configuración inicial — SPJ ERP/POS", width=DialogMetrics.WIDTH_MD)
        self.setModal(True)

        self._presenter = presenter
        self._view_model = ProvisioningViewModel()
        self._result: ProvisioningResult | None = None
        self._provisioned = False

        self._pages = [
            WelcomePage(self),
            CompanyPage(self),
            BranchPage(self),
            WorkstationPage(self),
            OwnerAccountPage(self, password_policy=password_policy),
            SecurityRecoveryPage(self),
            ConfirmationPage(self),
        ]
        self._confirmation_page: ConfirmationPage = self._pages[-1]
        self._confirmation_page.acknowledgement_changed.connect(lambda _ack: self._refresh_navigation())

        self._stack = QStackedWidget(self)
        for page in self._pages:
            self._stack.addWidget(page)
        self.content_layout().addWidget(self._stack, stretch=1)

        self._error_label = QLabel(self)
        self._error_label.setWordWrap(True)
        self._error_label.setProperty("role", "error")
        self._error_label.setVisible(False)
        self.content_layout().addWidget(self._error_label)

        self._cancel_btn = create_ghost_button(self, "Cancelar")
        self._back_btn = create_secondary_button(self, "Atrás")
        self._next_btn = create_primary_button(self, "Siguiente")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)

        footer = QHBoxLayout()
        footer.setSpacing(Spacing.SM)
        footer.addWidget(self._cancel_btn)
        footer.addStretch(1)
        footer.addWidget(self._back_btn)
        footer.addWidget(self._next_btn)
        self.content_layout().addLayout(footer)

        self._current_index = 0
        self._refresh_navigation()

    # ── Navigation ───────────────────────────────────────────────────────────

    def _current_page(self):
        return self._pages[self._current_index]

    def _at_confirmation(self) -> bool:
        return self._current_index == len(self._pages) - 1

    def _go_back(self) -> None:
        if self._provisioned or self._current_index == 0:
            return
        self._current_index -= 1
        self._stack.setCurrentIndex(self._current_index)
        self._error_label.setVisible(False)
        self._refresh_navigation()

    def _go_next(self) -> None:
        if self._provisioned:
            self.accept()
            return

        page = self._current_page()
        errors = page.validate()
        if errors:
            self._show_errors(errors)
            return
        self._error_label.setVisible(False)
        for key, value in page.values().items():
            setattr(self._view_model, key, value)

        if self._at_confirmation():
            self._finish()
            return

        self._current_index += 1
        self._stack.setCurrentIndex(self._current_index)
        if self._at_confirmation():
            self._confirmation_page.set_summary(self._view_model)
        self._refresh_navigation()

    def _finish(self) -> None:
        try:
            result = self._presenter.finish(self._view_model)
        except Exception as exc:  # noqa: BLE001 - translated to Spanish below, never swallowed
            self._show_errors([self._error_message_for(exc)])
            return
        self._result = result
        self._provisioned = True
        self._confirmation_page.show_result(result)
        self._refresh_navigation()

    def _on_cancel(self) -> None:
        if self._provisioned:
            return
        self.reject()

    def _refresh_navigation(self) -> None:
        self._cancel_btn.setVisible(not self._provisioned)
        self._back_btn.setVisible(not self._provisioned)
        self._back_btn.setEnabled(self._current_index > 0)
        if self._provisioned:
            self._next_btn.setText("Cerrar")
            self._next_btn.setEnabled(self._confirmation_page.is_acknowledged())
        elif self._at_confirmation():
            self._next_btn.setText("Finalizar")
            self._next_btn.setEnabled(True)
        else:
            self._next_btn.setText("Siguiente")
            self._next_btn.setEnabled(True)

    def _show_errors(self, errors: list[str]) -> None:
        self._error_label.setText("\n".join(f"• {e}" for e in errors))
        self._error_label.setVisible(True)

    @staticmethod
    def _error_message_for(exc: Exception) -> str:
        if isinstance(exc, PasswordPolicyViolationError):
            return "; ".join(exc.violations)
        if isinstance(exc, (OwnerUsernameTakenError, InstallationAlreadyProvisionedError,
                             InstallationLockedError, ValueError)):
            return str(exc)
        return f"No se pudo completar la configuración inicial: {exc}"

    # ── Close protection ─────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._provisioned and not self._confirmation_page.is_acknowledged():
            event.ignore()
            self._show_errors([
                "Confirme que guardó sus códigos de recuperación antes de cerrar.",
            ])
            return
        super().closeEvent(event)

    # ── Result access ────────────────────────────────────────────────────────

    def provisioning_result(self) -> ProvisioningResult | None:
        return self._result
