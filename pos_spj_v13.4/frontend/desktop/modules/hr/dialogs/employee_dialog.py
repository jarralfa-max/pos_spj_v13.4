"""Canonical employee dialog for HR create/update flows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from frontend.desktop.modules.hr.hr_view_models import HRCatalogOptionViewModel, HREmployeeFormOptionsViewModel, HREmployeeFormViewModel
from frontend.desktop.themes import DesktopSpacing


class HREmployeeDialog(QDialog):
    """Captures employee data using configurable catalog options."""

    def __init__(self, options: HREmployeeFormOptionsViewModel, parent=None, *, initial: HREmployeeFormViewModel | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Empleado")
        self._code = QLineEdit(self)
        self._first_name = QLineEdit(self)
        self._last_name = QLineEdit(self)
        self._phone = QLineEdit(self)
        self._email = QLineEdit(self)
        self._branch_id = QLineEdit(self)
        self._department = QComboBox(self)
        self._position = QComboBox(self)
        self._contract_type = QComboBox(self)
        self._payment_frequency = QComboBox(self)
        self._base_salary = QLineEdit(self)
        self._daily_salary = QLineEdit(self)
        self._hire_date = QDateEdit(self)
        self._hire_date.setCalendarPopup(True)

        self._fill_combo(self._department, options.departments)
        self._fill_combo(self._position, options.positions)
        self._fill_combo(self._contract_type, options.contract_types)
        self._fill_combo(self._payment_frequency, options.payment_frequencies)

        root = QVBoxLayout(self)
        root.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        form = QFormLayout()
        form.addRow("Código", self._code)
        form.addRow("Nombre", self._first_name)
        form.addRow("Apellido", self._last_name)
        form.addRow("Teléfono", self._phone)
        form.addRow("Email", self._email)
        form.addRow("Sucursal", self._branch_id)
        form.addRow("Departamento", self._department)
        form.addRow("Puesto", self._position)
        form.addRow("Tipo de contrato", self._contract_type)
        form.addRow("Periodicidad", self._payment_frequency)
        form.addRow("Salario base", self._base_salary)
        form.addRow("Salario diario", self._daily_salary)
        form.addRow("Fecha de ingreso", self._hire_date)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        if initial is not None:
            self.set_form(initial)

    def form(self) -> HREmployeeFormViewModel:
        return HREmployeeFormViewModel(
            employee_code=self._code.text().strip(),
            first_name=self._first_name.text().strip(),
            last_name=self._last_name.text().strip(),
            phone_e164=self._optional(self._phone.text()),
            email=self._optional(self._email.text()),
            branch_id=self._branch_id.text().strip(),
            department_id=self._department.currentData(),
            position_id=self._position.currentData(),
            contract_type=self._contract_type.currentData(),
            payment_frequency=self._payment_frequency.currentData(),
            base_salary=Decimal(self._base_salary.text().strip() or "0"),
            daily_salary=Decimal(self._daily_salary.text().strip() or "0"),
            hire_date=self._hire_date.date().toPyDate(),
        )

    def set_form(self, form: HREmployeeFormViewModel) -> None:
        self._code.setText(form.employee_code)
        self._first_name.setText(form.first_name)
        self._last_name.setText(form.last_name)
        self._phone.setText(form.phone_e164 or "")
        self._email.setText(form.email or "")
        self._branch_id.setText(form.branch_id)
        self._base_salary.setText(str(form.base_salary))
        self._daily_salary.setText(str(form.daily_salary))
        self._hire_date.setDate(QDate(form.hire_date.year, form.hire_date.month, form.hire_date.day))
        self._select(self._department, form.department_id)
        self._select(self._position, form.position_id)
        self._select(self._contract_type, form.contract_type)
        self._select(self._payment_frequency, form.payment_frequency)

    def _fill_combo(self, combo: QComboBox, options: tuple[HRCatalogOptionViewModel, ...]) -> None:
        combo.clear()
        for option in options:
            combo.addItem(option.label, option.id)

    def _select(self, combo: QComboBox, option_id: str) -> None:
        index = combo.findData(option_id)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _optional(self, value: str) -> str | None:
        cleaned = value.strip()
        return cleaned or None
