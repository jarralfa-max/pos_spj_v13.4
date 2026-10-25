"""Alta de presupuesto (§16): partidas por cuenta y periodo.

El presupuesto nace en BORRADOR; enviarlo, aprobarlo y activarlo son pasos
separados. «Bloqueante» decide si un gasto que lo excede se rechaza o sólo
avisa.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QWidget,
)

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.month_input import MonthInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class BudgetDialog(FinanceFormDialog):
    dialog_title = "Nuevo presupuesto"

    def __init__(self, parent, expense_accounts: list[tuple[str, str]], year: int) -> None:
        self._accounts = expense_accounts
        self._year = year
        super().__init__(parent)
        self.setMinimumWidth(720)

    def _build_form(self) -> None:
        self.name_input = QLineEdit(self)
        self.year_input = QSpinBox(self)
        self.year_input.setRange(2000, 2100)
        self.year_input.setValue(self._year)
        self.blocking_check = QCheckBox("Bloqueante (un gasto que lo excede se rechaza)", self)
        self.blocking_check.setChecked(True)
        self.form.addRow("Nombre *:", self.name_input)
        self.form.addRow("Año fiscal:", self.year_input)
        self.form.addRow(self.blocking_check)
        self.lines = QTableWidget(0, 3, self)
        self.lines.setHorizontalHeaderLabels(["Cuenta", "Periodo", "Importe"])
        self.lines.horizontalHeader().setStretchLastSection(True)
        self.lines.setMinimumHeight(200)
        self.form.addRow(self.lines)
        buttons = QWidget(self)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        add = create_secondary_button(self, "Agregar partida")
        add.clicked.connect(self.add_line)
        remove = create_secondary_button(self, "Quitar partida")
        remove.clicked.connect(lambda: self.lines.removeRow(self.lines.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        self.form.addRow(buttons)
        self.add_line()

    def add_line(self) -> None:
        row = self.lines.rowCount()
        self.lines.insertRow(row)
        combo = QComboBox(self.lines)
        for value, label in self._accounts:
            combo.addItem(label, value)
        self.lines.setCellWidget(row, 0, combo)
        self.lines.setCellWidget(row, 1, MonthInput(self.lines))
        amount = QLineEdit(self.lines)
        amount.setPlaceholderText("0.00")
        self.lines.setCellWidget(row, 2, amount)

    def _rows(self) -> list[dict]:
        result = []
        for row in range(self.lines.rowCount()):
            text = self.lines.cellWidget(row, 2).text().strip()
            if not text:
                continue
            result.append({"account_id": self.lines.cellWidget(row, 0).currentData(),
                           "period_code": self.lines.cellWidget(row, 1).month_text(),
                           "planned_amount": format(Decimal(text), "f")})
        return result

    def _validation_error(self) -> str | None:
        if not self.name_input.text().strip():
            return "Escriba el nombre del presupuesto."
        try:
            rows = self._rows()
        except InvalidOperation:
            return "Hay un importe inválido."
        if not rows:
            return "Capture al menos una partida con importe."
        for line in rows:
            if Decimal(line["planned_amount"]) <= 0:
                return "Cada partida debe tener un importe mayor que cero."
            if not line["period_code"].startswith(str(self.year_input.value())):
                return f"El periodo {line['period_code']} no pertenece al año fiscal."
        return None

    def data(self) -> dict:
        return {"name": self.name_input.text().strip(), "fiscal_year": self.year_input.value(),
                "blocking": self.blocking_check.isChecked(), "lines": self._rows()}
