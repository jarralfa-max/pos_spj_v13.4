"""owner_account_page — InitialSetupWizard step 5/7.

Captures the first (SYSTEM_OWNER) account. No suggested/prefilled password —
`PasswordPolicy` is enforced client-side for immediate feedback, and again
server-side by `ProvisionInstallationUseCase` (never trust the UI check
alone).
"""
from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QLabel

from backend.security.credentials.errors import PasswordPolicyViolationError
from backend.security.credentials.password_policy import PasswordPolicy
from frontend.desktop.components.text_inputs import PasswordInput, StandardLineEdit
from frontend.desktop.provisioning.pages._wizard_page import WizardPage


class OwnerAccountPage(WizardPage):
    def __init__(self, parent=None, *, password_policy: PasswordPolicy | None = None) -> None:
        super().__init__(
            parent, title="Cuenta del propietario",
            subtitle="La primera cuenta del sistema — acceso total (rol Propietario del sistema).",
        )
        self._policy = password_policy or PasswordPolicy()

        form = QFormLayout()
        self.full_name = StandardLineEdit(
            self, placeholder="Nombre completo", required=True,
            accessible_name="Nombre completo del propietario",
        )
        self.username = StandardLineEdit(
            self, placeholder="Nombre de usuario", required=True,
            accessible_name="Nombre de usuario",
        )
        self.password = PasswordInput(self, placeholder="Contraseña")
        self.password_confirm = PasswordInput(self, placeholder="Confirmar contraseña")

        form.addRow("Nombre completo *", self.full_name)
        form.addRow("Usuario *", self.username)
        form.addRow("Contraseña *", self.password)
        form.addRow("Confirmar contraseña *", self.password_confirm)
        self.body_layout().addLayout(form)

        self._policy_hint = QLabel(self._policy_hint_text(), self)
        self._policy_hint.setWordWrap(True)
        self._policy_hint.setProperty("role", "hint")
        self.body_layout().addWidget(self._policy_hint)
        self.body_layout().addStretch(1)

    def _policy_hint_text(self) -> str:
        p = self._policy
        parts = [f"Mínimo {p.minimum_length} caracteres"]
        if p.require_uppercase:
            parts.append("una mayúscula")
        if p.require_lowercase:
            parts.append("una minúscula")
        if p.require_number:
            parts.append("un número")
        if p.require_symbol:
            parts.append("un símbolo")
        return "La contraseña debe incluir: " + ", ".join(parts) + "."

    def values(self) -> dict:
        return {
            "owner_full_name": self.full_name.value(),
            "owner_username": self.username.value(),
            "owner_password": self.password.value(),
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.full_name.is_valid():
            errors.append("El nombre completo es obligatorio.")
        if not self.username.is_valid():
            errors.append("El nombre de usuario es obligatorio.")
        if self.password.value() != self.password_confirm.value():
            errors.append("La contraseña y su confirmación no coinciden.")
        elif self.password.value():
            try:
                self._policy.validate(self.password.value(), username=self.username.value())
            except PasswordPolicyViolationError as exc:
                errors.extend(exc.violations)
        else:
            errors.append("La contraseña es obligatoria.")
        return errors
