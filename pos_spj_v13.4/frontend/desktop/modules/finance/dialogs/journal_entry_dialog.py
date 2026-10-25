"""Captura de asiento manual (§8.2): encabezado + renglones debe/haber.

El diálogo no decide nada contable: suma con ``Decimal`` para avisar si no
cuadra, y el caso de uso vuelve a validar partida doble, cuentas de detalle
activas, periodo y moneda. El asiento nace en BORRADOR; validarlo y
contabilizarlo son pasos separados (segregación §28).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QWidget,
)

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.date_input import DateInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


def _amount(text: str) -> Decimal:
    text = (text or "").strip().replace(",", "")
    if not text:
        return Decimal("0")
    return Decimal(text)


class JournalEntryDialog(FinanceFormDialog):
    dialog_title = "Asiento manual"

    def __init__(self, parent, *, accounts: list[tuple[str, str]],
                 journals: list[tuple[str, str]], currencies: list[tuple[str, str]],
                 base_currency: str = "MXN") -> None:
        self._accounts = accounts
        self._journals = journals
        self._currencies = currencies
        self._base_currency = base_currency
        super().__init__(parent)
        self.setMinimumWidth(820)

    def _build_form(self) -> None:
        self.date_input = DateInput(self)
        self.description_input = QLineEdit(self)
        self.journal_combo = QComboBox(self)
        for value, label in self._journals:
            self.journal_combo.addItem(label, value)
        index = self.journal_combo.findData("GENERAL")
        self.journal_combo.setCurrentIndex(max(index, 0))
        self.currency_combo = QComboBox(self)
        for value, label in self._currencies:
            self.currency_combo.addItem(label, value)
        self.currency_combo.setCurrentIndex(max(self.currency_combo.findData(self._base_currency),
                                                0))
        self.rate_input = QLineEdit(self)
        self.rate_input.setPlaceholderText("Vacío: tipo de cambio registrado del día")
        self.form.addRow("Fecha:", self.date_input)
        self.form.addRow("Concepto *:", self.description_input)
        self.form.addRow("Diario:", self.journal_combo)
        self.form.addRow("Moneda:", self.currency_combo)
        self.form.addRow("Tipo de cambio:", self.rate_input)

        self.lines = QTableWidget(0, 4, self)
        self.lines.setHorizontalHeaderLabels(["Cuenta", "Concepto", "Debe", "Haber"])
        self.lines.horizontalHeader().setStretchLastSection(True)
        self.lines.setMinimumHeight(220)
        self.form.addRow(self.lines)

        buttons = QWidget(self)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        add = create_secondary_button(self, "Agregar renglón")
        add.clicked.connect(self.add_line)
        remove = create_secondary_button(self, "Quitar renglón")
        remove.clicked.connect(self._remove_line)
        self.totals_label = QLabel("", self)
        self.totals_label.setProperty("role", "muted")
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        row.addWidget(self.totals_label)
        self.form.addRow(buttons)
        self.add_line()
        self.add_line()

    def add_line(self) -> None:
        row = self.lines.rowCount()
        self.lines.insertRow(row)
        combo = QComboBox(self.lines)
        combo.addItem("Elija una cuenta…", None)
        for value, label in self._accounts:
            combo.addItem(label, value)
        self.lines.setCellWidget(row, 0, combo)
        for column in (1, 2, 3):
            editor = QLineEdit(self.lines)
            if column > 1:
                editor.setPlaceholderText("0.00")
                editor.textChanged.connect(self._refresh_totals)
            self.lines.setCellWidget(row, column, editor)

    def _remove_line(self) -> None:
        row = self.lines.currentRow()
        if row >= 0:
            self.lines.removeRow(row)
            self._refresh_totals()

    def _cell(self, row: int, column: int) -> str:
        return self.lines.cellWidget(row, column).text().strip()

    def _totals(self) -> tuple[Decimal, Decimal]:
        debit = credit = Decimal("0")
        for row in range(self.lines.rowCount()):
            debit += _amount(self._cell(row, 2))
            credit += _amount(self._cell(row, 3))
        return debit, credit

    def _refresh_totals(self) -> None:
        try:
            debit, credit = self._totals()
        except InvalidOperation:
            self.totals_label.setText("Importe inválido")
            return
        difference = debit - credit
        self.totals_label.setText(f"Debe {debit:,.2f} · Haber {credit:,.2f} · "
                                  f"Diferencia {difference:,.2f}")

    def _validation_error(self) -> str | None:
        if not self.description_input.text().strip():
            return "Escriba el concepto del asiento."
        rate = self.rate_input.text().strip()
        if rate:
            try:
                if Decimal(rate) <= 0:
                    return "El tipo de cambio debe ser mayor que cero."
            except InvalidOperation:
                return "El tipo de cambio debe ser un número decimal."
        used = 0
        for row in range(self.lines.rowCount()):
            account = self.lines.cellWidget(row, 0).currentData()
            try:
                debit, credit = _amount(self._cell(row, 2)), _amount(self._cell(row, 3))
            except InvalidOperation:
                return f"Renglón {row + 1}: importe inválido."
            if not account and not debit and not credit:
                continue
            if not account:
                return f"Renglón {row + 1}: elija la cuenta."
            if (debit > 0) == (credit > 0) or debit < 0 or credit < 0:
                return f"Renglón {row + 1}: capture un importe en Debe o en Haber (uno solo)."
            used += 1
        if used < 2:
            return "Un asiento necesita al menos dos renglones."
        debit, credit = self._totals()
        if debit != credit:
            return f"El asiento no cuadra: debe {debit} y haber {credit}."
        return None

    def data(self) -> dict:
        lines = []
        for row in range(self.lines.rowCount()):
            account = self.lines.cellWidget(row, 0).currentData()
            if not account:
                continue
            debit, credit = _amount(self._cell(row, 2)), _amount(self._cell(row, 3))
            lines.append({"account_id": account, "description": self._cell(row, 1),
                          "debit": format(debit, "f") if debit else "",
                          "credit": format(credit, "f") if credit else ""})
        return {
            "entry_date": self.date_input.date_value(),
            "description": self.description_input.text().strip(),
            "journal_type": self.journal_combo.currentData(),
            "currency_code": self.currency_combo.currentData() or self._base_currency,
            "exchange_rate": self.rate_input.text().strip() or None,
            "lines": lines,
        }
