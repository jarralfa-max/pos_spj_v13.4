"""LoginWindow — SHELL-7 §39.

Receives `AuthenticateUserUseCase`, `BeginAccountRecoveryUseCase`,
`InstallationSummaryQueryService` — plus `CompleteAccountRecoveryUseCase`,
needed for `AccountRecoveryDialog` to actually finish the recovery flow
`BeginAccountRecoveryUseCase` starts (§39 doesn't list it explicitly, but a
"forgot password" link that can request a token and never complete the
reset isn't a working recovery flow). Never receives a database
connection, `AuthRepository`, `AppContainer`, a raw `password_hash`, or a
`SecretStore` — this window only captures credentials and shows results.

Built on the actual design system (`PageHeader`, `create_primary_button`,
`PasswordInput`) rather than the legacy `DialogoLogin`'s frameless
hand-painted `QDialog` with inline hex-color stylesheets — same direction
`InitialSetupWizard` (SHELL-2) already took.
"""
from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QLabel, QVBoxLayout

from backend.security.authentication.authenticate_user_use_case import (
    AuthenticateUserUseCase,
    AuthenticationResult,
)
from backend.security.authentication.errors import AuthenticationFailedError
from backend.security.provisioning.installation_summary_query import InstallationSummaryQueryService
from backend.security.recovery.begin_account_recovery_use_case import BeginAccountRecoveryUseCase
from backend.security.recovery.complete_account_recovery_use_case import CompleteAccountRecoveryUseCase
from backend.security.sessions.errors import AccountLockedError
from frontend.desktop.auth.account_recovery_dialog import AccountRecoveryDialog
from frontend.desktop.components.buttons import create_ghost_button, create_primary_button
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit
from frontend.desktop.themes.tokens import DialogMetrics


class LoginWindow(StandardDialog):
    def __init__(
        self, parent=None,
        *,
        authenticate_use_case: AuthenticateUserUseCase,
        begin_recovery_use_case: BeginAccountRecoveryUseCase,
        complete_recovery_use_case: CompleteAccountRecoveryUseCase,
        installation_summary_query: InstallationSummaryQueryService,
        workstation_id: str = "",
    ) -> None:
        super().__init__(parent, title="Iniciar sesión", width=DialogMetrics.WIDTH_SM)
        self.setModal(True)
        self._authenticate = authenticate_use_case
        self._begin_recovery = begin_recovery_use_case
        self._complete_recovery = complete_recovery_use_case
        self._workstation_id = workstation_id
        self.authentication_result: AuthenticationResult | None = None

        summary = installation_summary_query.get_summary()
        header_subtitle = summary.company_name
        if summary.branch_name:
            header_subtitle = f"{summary.company_name} — {summary.branch_name}"
        self.content_layout().addWidget(
            PageHeader(self, title="SPJ ERP/POS", subtitle=header_subtitle, compact=True)
        )

        form = QFormLayout()
        self._username_input = StandardLineEdit(self, placeholder="Usuario", required=True)
        self._password_input = PasswordInput(self, placeholder="Contraseña")
        form.addRow("Usuario", self._username_input)
        form.addRow("Contraseña", self._password_input)
        self.content_layout().addLayout(form)

        self._error_label = QLabel(self)
        self._error_label.setWordWrap(True)
        self._error_label.setProperty("role", "error")
        self._error_label.setVisible(False)
        self.content_layout().addWidget(self._error_label)

        self._login_btn = create_primary_button(self, "Iniciar sesión")
        self._login_btn.setDefault(True)
        self._login_btn.clicked.connect(self._on_login)
        self.content_layout().addWidget(self._login_btn)

        forgot_btn = create_ghost_button(self, "¿Olvidó su contraseña?")
        forgot_btn.clicked.connect(self._on_forgot_password)
        self.content_layout().addWidget(forgot_btn)

        self._password_input.returnPressed.connect(self._on_login)

    def _on_login(self) -> None:
        username = self._username_input.value()
        password = self._password_input.value()
        if not username or not password:
            self._show_error("Ingrese usuario y contraseña.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("Iniciando sesión...")
        try:
            self.authentication_result = self._authenticate.execute(
                username=username, password=password, workstation_id=self._workstation_id,
            )
        except AccountLockedError as exc:
            self._show_error(str(exc))
            return
        except AuthenticationFailedError as exc:
            self._show_error(str(exc))
            return
        finally:
            self._login_btn.setEnabled(True)
            self._login_btn.setText("Iniciar sesión")

        self._error_label.setVisible(False)
        self.accept()

    def _on_forgot_password(self) -> None:
        dialog = AccountRecoveryDialog(
            self, begin_use_case=self._begin_recovery, complete_use_case=self._complete_recovery,
        )
        dialog.exec_()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)
        self._password_input.clear()
