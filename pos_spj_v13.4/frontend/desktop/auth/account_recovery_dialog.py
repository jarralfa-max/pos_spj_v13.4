"""AccountRecoveryDialog — SHELL-7 "Recovery".

Two steps: request a token (`BeginAccountRecoveryUseCase`), then set a new
password with it (`CompleteAccountRecoveryUseCase`) — both SHELL-1
services, unchanged, now actually reachable from the UI.

No email/SMS delivery integration exists anywhere in this codebase yet
(confirmed before writing this — that's a separate integration, out of
scope here). Until one exists, the raw token is shown directly in step 1
as an interim, administrator-assisted flow (the user reads it off the
screen or has an admin relay it) rather than pretending delivery happens.
Wiring a real channel means step 1 stops displaying the token and instead
shows a generic "check your recovery contact" message — a UI-only change
once that integration exists, this dialog's use-case wiring doesn't move.

Receives only the two use cases — never a database connection, repository,
or password hasher (same rule §39 states for LoginWindow).
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFormLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from backend.security.credentials.errors import PasswordPolicyViolationError
from backend.security.recovery.begin_account_recovery_use_case import BeginAccountRecoveryUseCase
from backend.security.recovery.complete_account_recovery_use_case import CompleteAccountRecoveryUseCase
from frontend.desktop.components.buttons import create_ghost_button, create_primary_button
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit
from frontend.desktop.themes.tokens import DialogMetrics

_REQUEST_STEP, _RESET_STEP = 0, 1


class AccountRecoveryDialog(StandardDialog):
    def __init__(
        self, parent=None, *,
        begin_use_case: BeginAccountRecoveryUseCase,
        complete_use_case: CompleteAccountRecoveryUseCase,
    ) -> None:
        super().__init__(parent, title="Recuperar acceso", width=DialogMetrics.WIDTH_SM)
        self._begin_use_case = begin_use_case
        self._complete_use_case = complete_use_case
        self._raw_token = ""

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_request_step())
        self._stack.addWidget(self._build_reset_step())
        self.content_layout().addWidget(self._stack)

        self._error_label = QLabel(self)
        self._error_label.setWordWrap(True)
        self._error_label.setProperty("role", "error")
        self._error_label.setVisible(False)
        self.content_layout().addWidget(self._error_label)

    # ── Step 1: request ──────────────────────────────────────────────────────

    def _build_request_step(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        form = QFormLayout()
        self._username_input = StandardLineEdit(panel, placeholder="Usuario", required=True)
        form.addRow("Usuario *", self._username_input)
        layout.addLayout(form)

        send_btn = create_primary_button(panel, "Enviar código")
        send_btn.clicked.connect(self._on_request_token)
        layout.addWidget(send_btn)
        return panel

    def _on_request_token(self) -> None:
        username = self._username_input.value()
        if not username:
            self._show_error("Ingrese su nombre de usuario.")
            return
        try:
            self._raw_token = self._begin_use_case.execute(username)
        except Exception as exc:  # noqa: BLE001 - never reveal whether the user exists
            self._show_error(f"No se pudo generar el código: {exc}")
            return
        self._error_label.setVisible(False)
        self._token_display.setText(self._raw_token)
        self._stack.setCurrentIndex(_RESET_STEP)

    # ── Step 2: reset ────────────────────────────────────────────────────────

    def _build_reset_step(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)

        note = QLabel(
            "Código de recuperación (válido por tiempo limitado, un solo uso):",
            panel,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._token_display = QLabel(panel)
        self._token_display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._token_display.setProperty("role", "monospace")
        layout.addWidget(self._token_display)

        form = QFormLayout()
        self._new_password = PasswordInput(panel, placeholder="Nueva contraseña")
        self._confirm_password = PasswordInput(panel, placeholder="Confirmar contraseña")
        form.addRow("Nueva contraseña *", self._new_password)
        form.addRow("Confirmar *", self._confirm_password)
        layout.addLayout(form)

        reset_btn = create_primary_button(panel, "Restablecer contraseña")
        reset_btn.clicked.connect(self._on_reset_password)
        layout.addWidget(reset_btn)

        back_btn = create_ghost_button(panel, "Solicitar otro código")
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(_REQUEST_STEP))
        layout.addWidget(back_btn)
        return panel

    def _on_reset_password(self) -> None:
        if self._new_password.value() != self._confirm_password.value():
            self._show_error("La contraseña y su confirmación no coinciden.")
            return
        try:
            self._complete_use_case.execute(self._raw_token, self._new_password.value())
        except PasswordPolicyViolationError as exc:
            self._show_error("; ".join(exc.violations))
            return
        except Exception as exc:  # noqa: BLE001
            self._show_error(str(exc))
            return
        self._error_label.setVisible(False)
        self.accept()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(True)
