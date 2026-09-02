"""workstation_page — InitialSetupWizard step 4/7."""
from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout

from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.provisioning.pages._wizard_page import WizardPage


class WorkstationPage(WizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            parent, title="Estación de trabajo",
            subtitle="Nombre de esta computadora/caja — ayuda a identificarla en reportes.",
        )
        form = QFormLayout()
        self.workstation_name = StandardLineEdit(
            self, placeholder="Ej. Caja 1, Mostrador", required=True,
            accessible_name="Nombre de la estación de trabajo",
        )
        form.addRow("Nombre de la estación *", self.workstation_name)
        self.body_layout().addLayout(form)
        self.body_layout().addStretch(1)

    def values(self) -> dict:
        return {"workstation_name": self.workstation_name.value()}

    def validate(self) -> list[str]:
        errors = []
        if not self.workstation_name.is_valid():
            errors.append("El nombre de la estación de trabajo es obligatorio.")
        return errors
