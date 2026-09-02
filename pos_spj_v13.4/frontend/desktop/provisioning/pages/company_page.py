"""company_page — InitialSetupWizard step 2/7."""
from __future__ import annotations

from PyQt5.QtWidgets import QFormLayout

from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.provisioning.pages._wizard_page import WizardPage


class CompanyPage(WizardPage):
    def __init__(self, parent=None) -> None:
        super().__init__(
            parent, title="Empresa",
            subtitle="Datos de la empresa que usará este sistema.",
        )
        form = QFormLayout()
        self.company_name = StandardLineEdit(
            self, placeholder="Nombre de la empresa", required=True,
            accessible_name="Nombre de la empresa",
        )
        self.company_rfc = StandardLineEdit(
            self, placeholder="RFC (opcional)", max_length=13,
            accessible_name="RFC de la empresa",
        )
        form.addRow("Nombre de la empresa *", self.company_name)
        form.addRow("RFC", self.company_rfc)
        self.body_layout().addLayout(form)
        self.body_layout().addStretch(1)

    def values(self) -> dict:
        return {
            "company_name": self.company_name.value(),
            "company_rfc": self.company_rfc.value(),
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.company_name.is_valid():
            errors.append("El nombre de la empresa es obligatorio.")
        return errors
