"""confirmation_page — InitialSetupWizard step 7/7.

Two visual states, toggled by the wizard shell:

1. Review — a read-only summary of everything captured on the previous six
   pages, shown before the user clicks "Finalizar".
2. Result — after `ProvisioningPresenter.finish()` succeeds, replaces the
   summary with the one-time display of the recovery codes. The wizard may
   only be closed once `is_acknowledged()` is True — there is no way to see
   these codes again after this screen.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from backend.security.provisioning.provision_installation_use_case import ProvisioningResult
from frontend.desktop.provisioning.pages._wizard_page import WizardPage
from frontend.desktop.provisioning.provisioning_view_model import ProvisioningViewModel

_REVIEW_INDEX = 0
_RESULT_INDEX = 1


class ConfirmationPage(WizardPage):
    acknowledgement_changed = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent, title="Confirmación",
            subtitle="Revise los datos antes de finalizar.",
        )
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_review_panel())
        self._stack.addWidget(self._build_result_panel())
        self.body_layout().addWidget(self._stack, stretch=1)

    # ── Review panel ─────────────────────────────────────────────────────────

    def _build_review_panel(self) -> QWidget:
        panel = QWidget(self)
        form = QFormLayout(panel)
        self._summary_company = QLabel(panel)
        self._summary_branch = QLabel(panel)
        self._summary_workstation = QLabel(panel)
        self._summary_owner = QLabel(panel)
        self._summary_recovery_contact = QLabel(panel)
        form.addRow("Empresa:", self._summary_company)
        form.addRow("Sucursal inicial:", self._summary_branch)
        form.addRow("Estación:", self._summary_workstation)
        form.addRow("Propietario:", self._summary_owner)
        form.addRow("Correo de recuperación:", self._summary_recovery_contact)
        return panel

    def set_summary(self, view_model: ProvisioningViewModel) -> None:
        self._stack.setCurrentIndex(_REVIEW_INDEX)
        self._summary_company.setText(
            view_model.company_name + (f" (RFC {view_model.company_rfc})" if view_model.company_rfc else "")
        )
        self._summary_branch.setText(
            view_model.branch_name + (f" — {view_model.branch_address}" if view_model.branch_address else "")
        )
        self._summary_workstation.setText(view_model.workstation_name)
        self._summary_owner.setText(f"{view_model.owner_full_name} ({view_model.owner_username})")
        self._summary_recovery_contact.setText(view_model.owner_recovery_contact)

    # ── Result panel ─────────────────────────────────────────────────────────

    def _build_result_panel(self) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        warning = QLabel(
            "Estos códigos se muestran una única vez. Cada uno funciona una "
            "sola vez para recuperar el acceso a esta instalación si queda "
            "bloqueada. Guárdelos ahora — imprímalos o cópielos a un lugar seguro.",
            panel,
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        self._codes_grid = QGridLayout()
        self._codes_grid.setSpacing(8)
        layout.addLayout(self._codes_grid)

        self._acknowledge = QCheckBox(
            "He guardado mis códigos de recuperación en un lugar seguro.", panel,
        )
        self._acknowledge.stateChanged.connect(
            lambda _state: self.acknowledgement_changed.emit(self.is_acknowledged())
        )
        layout.addWidget(self._acknowledge)
        layout.addStretch(1)
        return panel

    def show_result(self, result: ProvisioningResult) -> None:
        self._stack.setCurrentIndex(_RESULT_INDEX)
        # clear any previous codes (defensive — should only render once)
        while self._codes_grid.count():
            item = self._codes_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for index, code in enumerate(result.recovery_codes):
            label = QLabel(code, self)
            label.setProperty("role", "monospace")
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._codes_grid.addWidget(label, index // 2, index % 2)
        self._acknowledge.setChecked(False)

    def is_acknowledged(self) -> bool:
        return self._acknowledge.isChecked()

    def values(self) -> dict:
        return {}

    def validate(self) -> list[str]:
        return []
