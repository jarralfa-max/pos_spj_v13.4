"""Diálogo de conciliación manual (match línea de estado ↔ línea contable)."""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox

from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class ReconciliationDialog(FinanceFormDialog):
    dialog_title = "Conciliar movimiento"

    def __init__(self, parent, statement_lines: list[tuple[str, str]],
                 ledger_lines: list[tuple[str, str]]) -> None:
        self._statement_lines = statement_lines
        self._ledger_lines = ledger_lines
        super().__init__(parent)

    def _build_form(self) -> None:
        self.statement_combo = QComboBox(self)
        for line_id, label in self._statement_lines:
            self.statement_combo.addItem(label, line_id)
        self.ledger_combo = QComboBox(self)
        for line_id, label in self._ledger_lines:
            self.ledger_combo.addItem(label, line_id)
        self.form.addRow("Línea del estado:", self.statement_combo)
        self.form.addRow("Línea contable:", self.ledger_combo)

    def _is_valid(self) -> bool:
        return bool(self.statement_combo.currentData() and self.ledger_combo.currentData())

    def data(self) -> dict:
        return {
            "bank_statement_line_id": self.statement_combo.currentData(),
            "journal_line_id": self.ledger_combo.currentData(),
        }
