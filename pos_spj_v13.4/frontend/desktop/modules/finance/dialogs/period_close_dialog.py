"""Diálogo de cierre de periodo (definitivo o pre-cierre)."""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QLabel

from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class PeriodCloseDialog(FinanceFormDialog):
    dialog_title = "Cerrar periodo contable"

    def _build_form(self) -> None:
        self.form.addRow(QLabel(
            "El cierre valida: asientos balanceados y conciliaciones completas.\n"
            "Un periodo cerrado no acepta contabilizaciones."))
        self.soft_checkbox = QCheckBox("Pre-cierre (SOFT_CLOSED)", self)
        self.form.addRow(self.soft_checkbox)

    def is_soft(self) -> bool:
        return self.soft_checkbox.isChecked()
