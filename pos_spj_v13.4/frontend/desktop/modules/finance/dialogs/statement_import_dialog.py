"""Captura de un estado de cuenta bancario para conciliar (auditoría F23).

Una partida por renglón: ``AAAA-MM-DD;descripción;importe;referencia`` (importe
con signo: positivo entra, negativo sale). El saldo inicial más las partidas
debe dar el saldo final; si no, el diálogo lo dice antes de enviar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QComboBox, QDateEdit, QLineEdit, QPlainTextEdit

from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class StatementImportDialog(FinanceFormDialog):
    dialog_title = "Importar estado de cuenta"

    def __init__(self, parent, treasury_accounts: list[tuple[str, str]]) -> None:
        self._accounts = treasury_accounts
        super().__init__(parent)

    def _build_form(self) -> None:
        self.account_combo = QComboBox(self)
        for account_id, label in self._accounts:
            self.account_combo.addItem(label, account_id)
        self.date_input = QDateEdit(QDate.currentDate(), self)
        self.date_input.setCalendarPopup(True)
        self.opening_input = QLineEdit("0.00", self)
        self.closing_input = QLineEdit("0.00", self)
        self.lines_input = QPlainTextEdit(self)
        self.lines_input.setPlaceholderText("2026-10-01;Depósito cliente;1500.00;SPEI123")
        self.form.addRow("Cuenta bancaria:", self.account_combo)
        self.form.addRow("Fecha del estado:", self.date_input)
        self.form.addRow("Saldo inicial:", self.opening_input)
        self.form.addRow("Saldo final:", self.closing_input)
        self.form.addRow("Partidas:", self.lines_input)

    def _parsed(self):
        lines = []
        for number, raw in enumerate(self.lines_input.toPlainText().splitlines(), start=1):
            if not raw.strip():
                continue
            parts = [p.strip() for p in raw.split(";")]
            if len(parts) < 3:
                raise ValueError(f"Renglón {number}: use fecha;descripción;importe;referencia")
            try:
                date.fromisoformat(parts[0])
                amount = Decimal(parts[2])
            except (ValueError, InvalidOperation):
                raise ValueError(f"Renglón {number}: fecha o importe inválido") from None
            lines.append({"transaction_date": parts[0], "description": parts[1],
                          "amount": format(amount, "f"),
                          "external_reference": parts[3] if len(parts) > 3 else ""})
        return lines

    def _validation_error(self) -> str | None:
        if not self.account_combo.currentData():
            return "Elija la cuenta bancaria del estado."
        try:
            opening = Decimal(self.opening_input.text().strip() or "0")
            closing = Decimal(self.closing_input.text().strip() or "0")
            lines = self._parsed()
        except InvalidOperation:
            return "Los saldos deben ser importes decimales."
        except ValueError as exc:
            return str(exc)
        if not lines:
            return "Capture al menos una partida."
        total = sum((Decimal(l["amount"]) for l in lines), Decimal("0"))
        if opening + total != closing:
            return (f"Saldo inicial {opening} + partidas {total} = {opening + total}, "
                    f"no el saldo final {closing}.")
        return None

    def data(self) -> dict:
        qdate = self.date_input.date()
        return {
            "treasury_account_id": self.account_combo.currentData(),
            "statement_date": date(qdate.year(), qdate.month(), qdate.day()),
            "opening_balance": self.opening_input.text().strip() or "0",
            "closing_balance": self.closing_input.text().strip() or "0",
            "lines": self._parsed(),
        }
