"""Canonical employee dialog for HR create/update flows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QDialogButtonBox, QDateEdit, QLineEdit

from frontend.desktop.components import DecimalInput, FormField, PhoneInput, SearchableComboBox, StandardDialog, StandardForm
from frontend.desktop.modules.hr.hr_view_models import HRCatalogOptionViewModel, HREmployeeFormOptionsViewModel, HREmployeeFormViewModel


class HREmployeeDialog(StandardDialog):
    """Captures employee data using canonical form fields and catalog selectors."""

    def __init__(self, options: HREmployeeFormOptionsViewModel, parent=None, *, initial: HREmployeeFormViewModel | None = None) -> None:
        self._form = StandardForm(parent)
        self._code = QLineEdit(parent)
        self._first_name = QLineEdit(parent)
        self._last_name = QLineEdit(parent)
        self._phone = PhoneInput(parent)
        self._email = QLineEdit(parent)
        self._branch_id = QLineEdit(parent)
        self._department = SearchableComboBox(parent, placeholder="Selecciona departamento…")
        self._position = SearchableComboBox(parent, placeholder="Selecciona puesto…")
        self._contract_type = SearchableComboBox(parent, placeholder="Selecciona tipo de contrato…")
        self._payment_frequency = SearchableComboBox(parent, placeholder="Selecciona periodicidad…")
        self._base_salary = DecimalInput(parent, decimals=2, step=Decimal("0.01"))
        self._daily_salary = DecimalInput(parent, decimals=2, step=Decimal("0.01"))
        self._hire_date = QDateEdit(parent)
        self._hire_date.setObjectName("dateInput")
        self._hire_date.setCalendarPopup(True)
        self._hire_date.setDate(QDate.currentDate())

        self._department.set_options(self._option_pairs(options.departments))
        self._position.set_options(self._option_pairs(options.positions))
        self._contract_type.set_options(self._option_pairs(options.contract_types))
        self._payment_frequency.set_options(self._option_pairs(options.payment_frequencies))
        self._build_form()

        super().__init__(
            parent,
            title="Empleado",
            description="Captura los datos obligatorios del empleado. Los catálogos deben seleccionarse explícitamente.",
            content=self._form,
            buttons=QDialogButtonBox.Save | QDialogButtonBox.Cancel,
        )
        self.set_initial_focus(self._code)
        if initial is not None:
            self.set_form(initial)

    def accept(self) -> None:
        if not self._validate():
            self._form.focus_first_error()
            return
        super().accept()

    def form(self) -> HREmployeeFormViewModel:
        return HREmployeeFormViewModel(
            employee_code=self._code.text().strip(),
            first_name=self._first_name.text().strip(),
            last_name=self._last_name.text().strip(),
            phone_e164=self._optional(self._phone.value()),
            email=self._optional(self._email.text()),
            branch_id=self._branch_id.text().strip(),
            department_id=self._department.selected_id() or "",
            position_id=self._position.selected_id() or "",
            contract_type=self._contract_type.selected_id() or "",
            payment_frequency=self._payment_frequency.selected_id() or "",
            base_salary=self._decimal_from_input(self._base_salary),
            daily_salary=self._decimal_from_input(self._daily_salary),
            hire_date=self._hire_date.date().toPyDate(),
        )

    def set_form(self, form: HREmployeeFormViewModel) -> None:
        self._code.setText(form.employee_code)
        self._first_name.setText(form.first_name)
        self._last_name.setText(form.last_name)
        self._phone.set_value(form.phone_e164 or "")
        self._email.setText(form.email or "")
        self._branch_id.setText(form.branch_id)
        self._base_salary.set_decimal_value(form.base_salary)
        self._daily_salary.set_decimal_value(form.daily_salary)
        self._hire_date.setDate(QDate(form.hire_date.year, form.hire_date.month, form.hire_date.day))
        self._select(self._department, form.department_id)
        self._select(self._position, form.position_id)
        self._select(self._contract_type, form.contract_type)
        self._select(self._payment_frequency, form.payment_frequency)

    def _build_form(self) -> None:
        self._form.add_field("code", FormField("Código", self._code, helper_text="Ej. EMP-001", required=True))
        self._form.add_field("first_name", FormField("Nombre", self._first_name, helper_text="Ej. Ana", required=True))
        self._form.add_field("last_name", FormField("Apellido", self._last_name, helper_text="Ej. Pérez", required=True))
        self._form.add_field("phone", FormField("Teléfono", self._phone, helper_text="Formato E.164, por ejemplo +525512345678."))
        self._form.add_field("email", FormField("Email", self._email, helper_text="Ej. ana.perez@empresa.com"))
        self._form.add_field("branch", FormField("Sucursal", self._branch_id, helper_text="UUID de sucursal hasta conectar BranchSearchBox.", required=True))
        self._form.add_field("department", FormField("Departamento", self._department, required=True))
        self._form.add_field("position", FormField("Puesto", self._position, required=True))
        self._form.add_field("contract_type", FormField("Tipo de contrato", self._contract_type, required=True))
        self._form.add_field("payment_frequency", FormField("Periodicidad", self._payment_frequency, required=True))
        self._form.add_field("base_salary", FormField("Salario base", self._base_salary, required=True))
        self._form.add_field("daily_salary", FormField("Salario diario", self._daily_salary, required=True))
        self._form.add_field("hire_date", FormField("Fecha de ingreso", self._hire_date, required=True))

    def _validate(self) -> bool:
        self._form.clear_errors()
        required_text = {
            "code": (self._code, "Captura el código del empleado."),
            "first_name": (self._first_name, "Captura el nombre del empleado."),
            "last_name": (self._last_name, "Captura el apellido del empleado."),
            "branch": (self._branch_id, "Captura una sucursal válida."),
        }
        for key, (widget, message) in required_text.items():
            if not widget.text().strip():
                self._form.set_error(key, message)
        if self._phone.value() and not self._phone.is_valid():
            self._form.set_error("phone", "Captura el teléfono en formato E.164, por ejemplo +525512345678.")
        for key, combo, message in (
            ("department", self._department, "Selecciona un departamento válido."),
            ("position", self._position, "Selecciona un puesto válido."),
            ("contract_type", self._contract_type, "Selecciona un tipo de contrato válido."),
            ("payment_frequency", self._payment_frequency, "Selecciona una periodicidad válida."),
        ):
            if combo.selected_id() is None:
                self._form.set_error(key, message)
        return not self._form.has_errors()

    def _option_pairs(self, options: tuple[HRCatalogOptionViewModel, ...]) -> tuple[tuple[str, str], ...]:
        return tuple((option.id, option.label) for option in options)

    def _select(self, combo: SearchableComboBox, option_id: str) -> None:
        index = combo.findData(option_id)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _decimal_from_input(self, widget: DecimalInput) -> Decimal:
        try:
            return widget.decimal_value()
        except InvalidOperation:
            return Decimal("0")

    def _optional(self, value: str) -> str | None:
        cleaned = value.strip()
        return cleaned or None
