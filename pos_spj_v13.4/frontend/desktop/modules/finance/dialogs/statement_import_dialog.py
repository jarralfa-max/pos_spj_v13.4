"""Importación de estado de cuenta (§15): archivo CSV/XLSX o captura controlada.

Las partidas se leen y se muestran ANTES de importar; el saldo inicial más las
partidas debe dar el saldo final, o el diálogo lo dice y no envía nada. Un
estado ya importado (mismo contenido) lo rechaza el caso de uso.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

from PyQt5.QtWidgets import QComboBox, QLabel, QLineEdit, QPlainTextEdit

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.file_path_input import FilePathInput
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class StatementImportDialog(FinanceFormDialog):
    dialog_title = "Importar estado de cuenta"

    def __init__(self, parent, treasury_accounts: list[tuple[str, str]], *,
                 read_file: Callable[[str], tuple[bool, object]],
                 parse_manual: Callable[[str], tuple[bool, object]]) -> None:
        self._accounts = treasury_accounts
        self._read_file = read_file
        self._parse_manual = parse_manual
        self._lines: list[dict] = []
        self._source = ("MANUAL", "")
        super().__init__(parent)
        self.setMinimumWidth(760)

    def _build_form(self) -> None:
        self.account_combo = QComboBox(self)
        for account_id, label in self._accounts:
            self.account_combo.addItem(label, account_id)
        self.date_input = DateInput(self)
        self.opening_input = QLineEdit("0.00", self)
        self.closing_input = QLineEdit("0.00", self)
        self.file_input = FilePathInput(self)
        self.file_input.set_file_filter("Estados de cuenta (*.csv *.xlsx *.xlsm)")
        self.file_input.path_changed.connect(self._load_file)
        self.lines_input = QPlainTextEdit(self)
        self.lines_input.setMaximumHeight(80)
        self.lines_input.setPlaceholderText("2026-10-01;Depósito cliente;1500.00;SPEI123")
        read_manual = create_secondary_button(self, "Leer captura")
        read_manual.clicked.connect(self._load_manual)
        self.preview = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Descripción"),
            ColumnSpec("Importe", "numeric"), ColumnSpec("Referencia", "date")], self)
        self.preview.setMinimumHeight(180)
        self.summary_label = QLabel("", self)
        self.summary_label.setProperty("role", "muted")
        self.form.addRow("Cuenta bancaria *:", self.account_combo)
        self.form.addRow("Fecha del estado:", self.date_input)
        self.form.addRow("Saldo inicial *:", self.opening_input)
        self.form.addRow("Saldo final *:", self.closing_input)
        self.form.addRow("Archivo CSV/XLSX:", self.file_input)
        self.form.addRow("O captura (fecha;descripción;importe;referencia):", self.lines_input)
        self.form.addRow(read_manual)
        self.form.addRow(self.preview)
        self.form.addRow(self.summary_label)

    def _show(self, lines: list[dict]) -> None:
        self._lines = lines
        self.preview.load_rows([[l["transaction_date"], l["description"], l["amount"],
                                 l.get("external_reference", "")] for l in lines])
        total = sum((Decimal(l["amount"]) for l in lines), Decimal("0"))
        self.summary_label.setText(f"{len(lines)} partidas · suma {total:,.2f}")

    def _load_file(self, path: str) -> None:
        if not path:
            return
        ok, result = self._read_file(path)
        if not ok:
            self.error_label.setText(str(result))
            self.error_label.show()
            return
        self.error_label.hide()
        self._source = (result.source_format, result.file_name)
        self._show(result.lines)

    def _load_manual(self) -> None:
        ok, result = self._parse_manual(self.lines_input.toPlainText())
        if not ok:
            self.error_label.setText(str(result))
            self.error_label.show()
            return
        self.error_label.hide()
        self._source = ("MANUAL", "")
        self._show(result)

    def _validation_error(self) -> str | None:
        if not self.account_combo.currentData():
            return "Elija la cuenta bancaria del estado."
        try:
            opening = Decimal(self.opening_input.text().strip() or "0")
            closing = Decimal(self.closing_input.text().strip() or "0")
        except InvalidOperation:
            return "Los saldos deben ser importes decimales."
        if not self._lines:
            return "Cargue un archivo o lea la captura: no hay partidas."
        total = sum((Decimal(l["amount"]) for l in self._lines), Decimal("0"))
        if opening + total != closing:
            return (f"Saldo inicial {opening} + partidas {total} = {opening + total}, "
                    f"no el saldo final {closing}.")
        return None

    def data(self) -> dict:
        return {
            "treasury_account_id": self.account_combo.currentData(),
            "statement_date": self.date_input.date_value(),
            "opening_balance": self.opening_input.text().strip() or "0",
            "closing_balance": self.closing_input.text().strip() or "0",
            "lines": self._lines,
            "source_format": self._source[0],
            "file_name": self._source[1],
        }
