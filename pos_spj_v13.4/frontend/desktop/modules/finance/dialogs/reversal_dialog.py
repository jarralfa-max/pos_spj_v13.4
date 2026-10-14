"""Diálogo de motivo para reversos y reaperturas (auditado)."""

from __future__ import annotations

from PyQt5.QtWidgets import QTextEdit

from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class ReversalDialog(FinanceFormDialog):
    dialog_title = "Motivo del reverso"

    def __init__(self, parent=None, title: str | None = None) -> None:
        if title:
            self.dialog_title = title
        super().__init__(parent)

    def _build_form(self) -> None:
        self.reason_input = QTextEdit(self)
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo (obligatorio):", self.reason_input)

    def _validation_error(self) -> str | None:
        if not self.reason_input.toPlainText().strip():
            return "Escriba el motivo: queda en la auditoría del asiento de reversión."
        return None

    def _is_valid(self) -> bool:
        return self._validation_error() is None

    def reason(self) -> str:
        return self.reason_input.toPlainText().strip()
