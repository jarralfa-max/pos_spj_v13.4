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

    def _is_valid(self) -> bool:
        return bool(self.reason_input.toPlainText().strip())

    def reason(self) -> str:
        return self.reason_input.toPlainText().strip()
