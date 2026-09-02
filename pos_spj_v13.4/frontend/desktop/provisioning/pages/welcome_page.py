"""welcome_page — InitialSetupWizard step 1/7."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from frontend.desktop.provisioning.pages._wizard_page import WizardPage


class WelcomePage(WizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            title="Bienvenido a SPJ ERP/POS",
            subtitle="Esta instalación aún no ha sido configurada.",
        )
        message = QLabel(
            "Este asistente configurará su empresa, la sucursal inicial, la "
            "estación de trabajo y la cuenta del propietario del sistema.\n\n"
            "Al finalizar recibirá un kit de recuperación con códigos de "
            "respaldo de un solo uso — guárdelos en un lugar seguro, se "
            "muestran una única vez.",
            self,
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.body_layout().addWidget(message)
        self.body_layout().addStretch(1)
