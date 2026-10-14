"""Ejecución de un pago a proveedor: evidencia obligatoria (auditoría F13).

EXECUTED declara que el pago salió con una evidencia verificable (folio SPEI,
número de cheque o recibo); sin ella el pago no se marca como ejecutado.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QLineEdit

from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class PaymentExecutionDialog(FinanceFormDialog):
    dialog_title = "Ejecutar pago"

    def __init__(self, parent, summary: str) -> None:
        self._summary = summary
        super().__init__(parent)

    def _build_form(self) -> None:
        summary = QLabel(self._summary, self)
        summary.setWordWrap(True)
        self.form.addRow(summary)
        self.reference_input = QLineEdit(self)
        self.reference_input.setPlaceholderText("Folio SPEI, cheque o recibo")
        self.form.addRow("Evidencia del pago:", self.reference_input)

    def _validation_error(self) -> str | None:
        if not self.reference_input.text().strip():
            return "Registre la evidencia externa del pago; sin ella no se ejecuta."
        return None

    def reference(self) -> str:
        return self.reference_input.text().strip()
