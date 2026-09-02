"""branch_page — InitialSetupWizard step 3/7."""
from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout

from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.provisioning.pages._wizard_page import WizardPage


class BranchPage(WizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            parent, title="Sucursal inicial",
            subtitle="La primera sucursal — podrá agregar más después desde Configuración.",
        )
        form = QFormLayout()
        self.branch_name = StandardLineEdit(
            self, placeholder="Nombre de la sucursal", required=True,
            accessible_name="Nombre de la sucursal",
        )
        self.branch_address = StandardLineEdit(
            self, placeholder="Dirección (opcional)",
            accessible_name="Dirección de la sucursal",
        )
        form.addRow("Nombre de la sucursal *", self.branch_name)
        form.addRow("Dirección", self.branch_address)
        self.body_layout().addLayout(form)
        self.body_layout().addStretch(1)

    def values(self) -> dict:
        return {
            "branch_name": self.branch_name.value(),
            "branch_address": self.branch_address.value(),
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.branch_name.is_valid():
            errors.append("El nombre de la sucursal es obligatorio.")
        return errors
