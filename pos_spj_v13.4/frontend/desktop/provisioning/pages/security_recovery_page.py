"""security_recovery_page — InitialSetupWizard step 6/7.

Captures the recovery contact used by `AccountRecoveryService` for future
password resets, and explains the installation-level recovery kit that gets
generated on the confirmation page (`InstallationRecoveryKit` — separate
concern: that one recovers the *installation* if it becomes LOCKED, this one
recovers a *forgotten password*).
"""
from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout, QLabel

from frontend.desktop.components.email_input import EmailInput
from frontend.desktop.provisioning.pages._wizard_page import WizardPage


class SecurityRecoveryPage(WizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            parent, title="Recuperación de acceso",
            subtitle="Cómo podrá recuperar el acceso si olvida su contraseña.",
        )
        form = QFormLayout()
        self.recovery_contact = EmailInput(self, required=True)
        form.addRow("Correo de recuperación *", self.recovery_contact)
        self.body_layout().addLayout(form)

        note = QLabel(
            "Al finalizar, el sistema también generará un kit de 10 códigos "
            "de respaldo para esta instalación. Cada código funciona una "
            "sola vez y se muestran únicamente en la siguiente pantalla — "
            "imprímalos o guárdelos en un lugar seguro.",
            self,
        )
        note.setWordWrap(True)
        self.body_layout().addWidget(note)
        self.body_layout().addStretch(1)

    def values(self) -> dict:
        return {"owner_recovery_contact": self.recovery_contact.email()}

    def validate(self) -> list[str]:
        errors = []
        if not self.recovery_contact.is_valid():
            errors.append(self.recovery_contact.error_message() or "El correo de recuperación no es válido.")
        return errors
