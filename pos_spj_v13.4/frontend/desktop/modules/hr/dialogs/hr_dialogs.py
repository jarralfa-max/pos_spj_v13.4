"""Concrete HR form dialogs. Pure UI: capture input, no business rules."""

from __future__ import annotations

from datetime import date, time

from PyQt5.QtCore import QDate, QDateTime, QTime
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTimeEdit,
)

from frontend.desktop.components import PhoneInput
from frontend.desktop.components.employee_search_box import EmployeeSearchBox
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.hr.dialogs._form_dialog import HRFormDialog
from frontend.desktop.modules.hr.hr_view_models import LEAVE_TYPE_ES, money_display

_CONTRACT_TYPES = [
    ("PERMANENT", "Indefinido"),
    ("FIXED_TERM", "Plazo fijo"),
    ("TEMPORARY", "Temporal"),
    ("INTERNSHIP", "Prácticas"),
    ("HOURLY", "Por horas"),
]
_FREQUENCIES = [
    ("WEEKLY", "Semanal"),
    ("BIWEEKLY", "Catorcenal"),
    ("SEMIMONTHLY", "Quincenal"),
    ("MONTHLY", "Mensual"),
]
_WEEKDAYS = [
    (0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"),
    (4, "Viernes"), (5, "Sábado"), (6, "Domingo"),
]
_PAYMENT_METHODS = [("CASH", "Efectivo"), ("BANK_TRANSFER", "Transferencia"),
                    ("CHECK", "Cheque")]


def _combo(options: list[tuple], *, empty: str | None = None) -> QComboBox:
    combo = QComboBox()
    if empty is not None:
        combo.addItem(empty, None)
    for value, label in options:
        combo.addItem(label, value)
    return combo


def _select(combo: QComboBox, value) -> None:
    index = combo.findData(value)
    if index >= 0:
        combo.setCurrentIndex(index)


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _pydate(edit: QDateEdit) -> date:
    qd = edit.date()
    return date(qd.year(), qd.month(), qd.day())


class _EmployeePicker(EmployeeSearchBox):
    """Selector de empleado por búsqueda (HR-28): no precarga el padrón; busca
    por código o nombre dentro del alcance de la sesión."""

    def __init__(self, search, parent=None) -> None:
        super().__init__(parent, provider=self._options)
        self._search = search
        self._selected_id: str | None = None
        self.selected.connect(self._chosen)
        self.text_edited.connect(lambda _text: self._clear_choice())
        self.refresh("")

    def _options(self, query: str):
        return [SearchOption(employee_id, label) for employee_id, label in self._search(query)]

    def _chosen(self, option) -> None:
        self._selected_id = option.id
        self.set_selected_label(option.label)

    def _clear_choice(self) -> None:
        self._selected_id = None

    def current_id(self) -> str | None:
        return self._selected_id

    def currentData(self) -> str | None:   # compatibilidad con el contrato de QComboBox
        return self._selected_id


class EmployeeDialog(HRFormDialog):
    dialog_title = "Nuevo empleado"

    def __init__(self, parent=None, *, on_submit=None, catalogs: dict | None = None,
                 employee: dict | None = None) -> None:
        self._catalogs = catalogs or {"departments": [], "positions": []}
        self._employee = employee
        if employee is not None:
            self.dialog_title = "Editar empleado"
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._code = QLineEdit()
        self._first = QLineEdit()
        self._last = QLineEdit()
        self._contract = _combo(_CONTRACT_TYPES)
        self._frequency = _combo(_FREQUENCIES)
        self._department = _combo(self._catalogs.get("departments", []), empty="—")
        self._position = _combo(self._catalogs.get("positions", []), empty="—")
        self._base = QLineEdit()
        self._base.setPlaceholderText("0.00")
        self._daily = QLineEdit()
        self._daily.setPlaceholderText("0.00")
        self._hire = QDateEdit(QDate.currentDate())
        self._hire.setCalendarPopup(True)
        # El campo de destino se llama `phone_e164`, pero un QLineEdit acepta
        # cualquier cosa: "55 1234 5678" se guardaria tal cual como si fuera
        # E.164. `PhoneInput` quita separadores en `value()` y sabe validar el
        # formato. Es el widget canonico para telefonos.
        self._phone = PhoneInput()
        self._email = QLineEdit()
        self._tax = QLineEdit()
        self._tax.setPlaceholderText("RFC")
        self._bank = QLineEdit()
        self._bank.setPlaceholderText("CLABE o cuenta")
        self._emergency_name = QLineEdit()
        self._emergency_phone = PhoneInput()
        self.form.addRow("Código", self._code)
        self.form.addRow("Nombre", self._first)
        self.form.addRow("Apellidos", self._last)
        self.form.addRow("Contrato", self._contract)
        self.form.addRow("Frecuencia de pago", self._frequency)
        self.form.addRow("Departamento", self._department)
        self.form.addRow("Puesto", self._position)
        self.form.addRow("Sueldo base", self._base)
        self.form.addRow("Sueldo diario", self._daily)
        self.form.addRow("Fecha de ingreso", self._hire)
        if self._employee is not None:
            self._salary_from = QDateEdit(QDate.currentDate())
            self._salary_from.setCalendarPopup(True)
            self._salary_reason = QLineEdit()
            self.form.addRow("Nuevo salario vigente desde", self._salary_from)
            self.form.addRow("Motivo del cambio de salario", self._salary_reason)
        self.form.addRow("Teléfono", self._phone)
        self.form.addRow("Correo", self._email)
        self.form.addRow("RFC", self._tax)
        self.form.addRow("Cuenta bancaria", self._bank)
        self.form.addRow("Contacto de emergencia", self._emergency_name)
        self.form.addRow("Teléfono de emergencia", self._emergency_phone)
        if self._employee is not None:
            self._prefill(self._employee)

    def _prefill(self, emp: dict) -> None:
        self._code.setText(emp.get("employee_code") or "")
        self._code.setReadOnly(True)
        self._first.setText(emp.get("first_name") or "")
        self._last.setText(emp.get("last_name") or "")
        _select(self._contract, emp.get("contract_type"))
        _select(self._frequency, emp.get("payment_frequency"))
        _select(self._department, emp.get("department_id"))
        _select(self._position, emp.get("position_id"))
        self._base.setText(str(emp.get("base_salary") or ""))
        self._daily.setText(str(emp.get("daily_salary") or ""))
        if emp.get("hire_date"):
            self._hire.setDate(_qdate(date.fromisoformat(str(emp["hire_date"]))))
        self._hire.setEnabled(False)
        self._contract.setEnabled(False)
        self._frequency.setEnabled(False)
        self._phone.set_value(emp.get("phone_e164") or None)
        self._emergency_phone.set_value(emp.get("emergency_contact_phone") or None)
        self._email.setText(emp.get("email") or "")
        self._tax.setText(emp.get("tax_identifier") or "")
        self._bank.setText(emp.get("bank_account_reference") or "")
        self._emergency_name.setText(emp.get("emergency_contact_name") or "")

    def _error(self) -> str | None:
        from decimal import Decimal, InvalidOperation
        if not self._code.text().strip():
            return "El código es obligatorio."
        if not self._first.text().strip() or not self._last.text().strip():
            return "El nombre y los apellidos son obligatorios."
        for field, label in ((self._base, "sueldo base"), (self._daily, "sueldo diario")):
            try:
                if Decimal(field.text().strip() or "0") < 0:
                    return f"El {label} no puede ser negativo."
            except InvalidOperation:
                return f"El {label} debe ser numérico."
        return None

    def values(self) -> dict:
        values = {
            "first_name": self._first.text().strip(),
            "last_name": self._last.text().strip(),
            "department_id": self._department.currentData(),
            "position_id": self._position.currentData(),
            "base_salary": self._base.text().strip() or "0.00",
            "daily_salary": self._daily.text().strip() or "0.00",
            "phone_e164": self._phone.value() or None,
            "email": self._email.text().strip() or None,
            "tax_identifier": self._tax.text().strip() or None,
            "bank_account_reference": self._bank.text().strip() or None,
            "emergency_contact_name": self._emergency_name.text().strip() or None,
            "emergency_contact_phone": self._emergency_phone.value() or None,
        }
        if self._employee is None:
            values.update({
                "employee_code": self._code.text().strip(),
                "contract_type": self._contract.currentData(),
                "payment_frequency": self._frequency.currentData(),
                "hire_date": _pydate(self._hire),
            })
            if not values["department_id"]:
                values.pop("department_id")
            if not values["position_id"]:
                values.pop("position_id")
        else:
            values["salary_effective_from"] = _pydate(self._salary_from)
            values["salary_change_reason"] = self._salary_reason.text().strip()
        return values


class ManualAttendanceDialog(HRFormDialog):
    dialog_title = "Registro manual de asistencia"

    def __init__(self, employee_search, parent=None, *, on_submit=None) -> None:
        self._employee_search = employee_search
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._employee = _EmployeePicker(self._employee_search, self)
        self._punch = _combo([("ENTRY", "Entrada"), ("EXIT", "Salida")])
        self._when = QDateTimeEdit(QDateTime.currentDateTime())
        self._when.setCalendarPopup(True)
        self._when.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._reason = QLineEdit()
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Tipo", self._punch)
        self.form.addRow("Fecha y hora (de la sucursal)", self._when)
        self.form.addRow("Motivo", self._reason)

    def _error(self) -> str | None:
        if self._employee.current_id() is None:
            return "Seleccione un empleado."
        if not self._reason.text().strip():
            return "El registro manual requiere un motivo."
        return None

    def values(self) -> dict:
        # HR-22: la hora capturada es la del RELOJ de la sucursal; se envía sin
        # zona y el caso de uso la interpreta en la zona de la sucursal. Antes
        # se etiquetaba como UTC: las 09:00 quedaban como 03:00 locales.
        local = self._when.dateTime().toPyDateTime().replace(tzinfo=None, second=0,
                                                              microsecond=0)
        return {
            "employee_id": self._employee.current_id(),
            "punch_type": self._punch.currentData(),
            "occurred_at": local,
            "reason": self._reason.text().strip(),
        }


class AdjustmentRequestDialog(HRFormDialog):
    """HR-30: solicitar la corrección desde la jornada (antes la pantalla de
    Ajustes sólo aprobaba solicitudes que no se podían crear)."""

    dialog_title = "Solicitar ajuste de asistencia"

    def __init__(self, workday: dict, parent=None, *, on_submit=None) -> None:
        self._workday = workday
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self.form.addRow("Empleado", QLabel(self._workday.get("employee_name") or ""))
        self.form.addRow("Jornada", QLabel(str(self._workday.get("work_date") or "")))
        self._field = _combo([("first_entry_at", "Hora de entrada"),
                              ("last_exit_at", "Hora de salida")])
        day = date.fromisoformat(str(self._workday["work_date"]))
        self._when = QDateTimeEdit(QDateTime(_qdate(day), QTime(9, 0)))
        self._when.setCalendarPopup(True)
        self._when.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._reason = QLineEdit()
        self.form.addRow("Campo", self._field)
        self.form.addRow("Hora correcta (de la sucursal)", self._when)
        self.form.addRow("Motivo", self._reason)

    def _error(self) -> str | None:
        if not self._reason.text().strip():
            return "El ajuste requiere un motivo."
        return None

    def values(self) -> dict:
        local = self._when.dateTime().toPyDateTime().replace(tzinfo=None, second=0,
                                                              microsecond=0)
        return {"workday_id": self._workday["id"], "field_name": self._field.currentData(),
                "requested_value": local, "reason": self._reason.text().strip()}


class ShiftDialog(HRFormDialog):
    dialog_title = "Nuevo turno"

    def _build_form(self) -> None:
        self._name = QLineEdit()
        self._start = QTimeEdit(QTime(9, 0))
        self._end = QTimeEdit(QTime(17, 0))
        self._break = QSpinBox()
        self._break.setRange(0, 480)
        self._tolerance = QSpinBox()
        self._tolerance.setRange(0, 120)
        self._tolerance.setValue(10)
        self.form.addRow("Nombre", self._name)
        self.form.addRow("Inicio", self._start)
        self.form.addRow("Fin", self._end)
        self.form.addRow("Descanso no pagado (min)", self._break)
        self.form.addRow("Tolerancia retardo (min)", self._tolerance)

    def _error(self) -> str | None:
        if not self._name.text().strip():
            return "El nombre del turno es obligatorio."
        return None

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "start_time": time(self._start.time().hour(), self._start.time().minute()),
            "end_time": time(self._end.time().hour(), self._end.time().minute()),
            "break_minutes": self._break.value(),
            "late_tolerance_minutes": self._tolerance.value(),
        }


class AssignShiftDialog(HRFormDialog):
    dialog_title = "Asignar turno"

    def __init__(self, employee_search, shift_options, parent=None, *, on_submit=None) -> None:
        self._employee_search = employee_search
        self._shift_options = shift_options
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        from PyQt5.QtWidgets import QCheckBox, QWidget, QHBoxLayout
        self._employee = _EmployeePicker(self._employee_search, self)
        self._shift = _combo(self._shift_options)
        self._from = QDateEdit(QDate.currentDate())
        self._from.setCalendarPopup(True)
        self._weekday_checks: list[tuple[int, QCheckBox]] = []
        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        for value, label in _WEEKDAYS:
            check = QCheckBox(label[:2])
            check.setToolTip(label)
            if value <= 4:
                check.setChecked(True)
            days_layout.addWidget(check)
            self._weekday_checks.append((value, check))
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Turno", self._shift)
        self.form.addRow("Vigente desde", self._from)
        self.form.addRow("Días", days_widget)

    def _error(self) -> str | None:
        if self._employee.current_id() is None:
            return "Seleccione un empleado."
        if self._shift.currentData() is None:
            return "Seleccione un turno."
        if not any(check.isChecked() for _, check in self._weekday_checks):
            return "Seleccione al menos un día."
        return None

    def values(self) -> dict:
        weekdays = tuple(value for value, check in self._weekday_checks if check.isChecked())
        return {
            "employee_id": self._employee.current_id(),
            "work_shift_id": self._shift.currentData(),
            "effective_from": _pydate(self._from),
            "weekdays": weekdays,
        }


class LeaveDialog(HRFormDialog):
    dialog_title = "Nueva solicitud"

    def __init__(self, employee_search, parent=None, *, on_submit=None,
                 balance_text=None) -> None:
        self._employee_search = employee_search
        self._balance_text = balance_text
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._employee = _EmployeePicker(self._employee_search, self)
        self._type = _combo([(k, v) for k, v in LEAVE_TYPE_ES.items()
                             if k in ("VACATION", "PAID_LEAVE", "UNPAID_LEAVE", "SICK_LEAVE",
                                      "ABSENCE_JUSTIFICATION")])
        self._start = QDateEdit(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._end = QDateEdit(QDate.currentDate())
        self._end.setCalendarPopup(True)
        self._reason = QLineEdit()
        self._balance = QLabel("")
        self._balance.setProperty("role", "muted")
        self._balance.setWordWrap(True)
        self._employee.selected.connect(lambda *_: self._show_balance())
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Saldo de vacaciones", self._balance)
        self.form.addRow("Tipo", self._type)
        self.form.addRow("Desde", self._start)
        self.form.addRow("Hasta", self._end)
        self.form.addRow("Motivo", self._reason)

    def _show_balance(self) -> None:
        if self._balance_text and self._employee.current_id():
            self._balance.setText(self._balance_text(self._employee.current_id()))

    def _error(self) -> str | None:
        if self._employee.current_id() is None:
            return "Seleccione un empleado."
        if self._end.date() < self._start.date():
            return "La fecha final no puede ser anterior a la inicial."
        if not self._reason.text().strip():
            return "La solicitud requiere un motivo."
        return None

    def values(self) -> dict:
        return {
            "employee_id": self._employee.current_id(),
            "leave_type": self._type.currentData(),
            "start_date": _pydate(self._start),
            "end_date": _pydate(self._end),
            "reason": self._reason.text().strip(),
        }


class GeneratePayrollDialog(HRFormDialog):
    dialog_title = "Generar corrida de nómina"

    def _build_form(self) -> None:
        today = QDate.currentDate()
        self._start = QDateEdit(QDate(today.year(), today.month(), 1))
        self._start.setCalendarPopup(True)
        self._end = QDateEdit(today)
        self._end.setCalendarPopup(True)
        self.form.addRow("Periodo desde", self._start)
        self.form.addRow("Periodo hasta", self._end)

    def _error(self) -> str | None:
        if self._end.date() < self._start.date():
            return "El fin del periodo no puede ser anterior al inicio."
        return None

    def values(self) -> dict:
        return {"period_start": _pydate(self._start), "period_end": _pydate(self._end)}


class PayrollDetailDialog(HRFormDialog):
    """HR-29: revisión de la corrida — neto POR EMPLEADO y cada concepto."""

    dialog_title = "Detalle de la corrida"

    def __init__(self, detail: dict, parent=None, *, on_receipt_pdf=None,
                 on_receipt_ticket=None) -> None:
        self._detail = detail
        self._on_receipt_pdf = on_receipt_pdf
        self._on_receipt_ticket = on_receipt_ticket
        super().__init__(parent)

    def _receipt_buttons(self, table) -> None:
        """Recibo del empleado seleccionado (o de todos si no hay selección)."""
        from PyQt5.QtWidgets import QHBoxLayout, QWidget
        from frontend.desktop.components.buttons import create_secondary_button
        if not (self._on_receipt_pdf or self._on_receipt_ticket):
            return
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self._receipt_message = QLabel("")
        self._receipt_message.setWordWrap(True)

        def selected():
            employee_id = table.selected_row_id()
            return [employee_id] if employee_id else None

        for text, callback in (("Recibo en PDF", self._on_receipt_pdf),
                               ("Imprimir recibo (ticket)", self._on_receipt_ticket)):
            if callback is None:
                continue
            button = create_secondary_button(row, text)
            button.clicked.connect(lambda _=False, cb=callback: self._receipt_message.setText(
                cb(selected())[1]))
            layout.addWidget(button)
        layout.addStretch(1)
        self.form.addRow(row)
        self.form.addRow(self._receipt_message)

    def _build_form(self) -> None:
        run, totals = self._detail["run"], self._detail["totals"]
        self.form.addRow("Periodo", QLabel(f"{run['period_start']} → {run['period_end']}"))
        self.form.addRow("Estado", QLabel(self._detail["status"]))
        self.setMinimumWidth(860)
        self.form.addRow("Neto total", QLabel(money_display(totals["net"])))
        if self._detail.get("negative_employees"):
            warning = QLabel(f"{self._detail['negative_employees']} empleado(s) con neto "
                             "negativo: no se puede autorizar ni pagar.")
            warning.setProperty("role", "error")
            self.form.addRow(warning)
        employees = StandardTable([ColumnSpec("Código"), ColumnSpec("Empleado"),
                                   ColumnSpec("Percepciones", "numeric"),
                                   ColumnSpec("Deducciones", "numeric"),
                                   ColumnSpec("Neto", "numeric"), ColumnSpec("Aviso")], self)
        employees.load_rows(self._detail["employees"].rows,
                            row_ids=self._detail["employees"].row_ids)
        self.form.addRow(employees)
        self._receipt_buttons(employees)
        lines = StandardTable([ColumnSpec("Empleado"), ColumnSpec("Concepto"),
                               ColumnSpec("Tipo"), ColumnSpec("Importe", "numeric"),
                               ColumnSpec("Detalle")], self)
        lines.load_rows(self._detail["lines"].rows)
        self.form.addRow(lines)
        payment = self._detail.get("payment")
        if payment:
            reference = payment.get("payment_reference") or ""
            self.form.addRow("Pago", QLabel(f"{payment['payment_method']} {reference}".strip()))
            if self._detail.get("accounting"):
                self.form.addRow("Contabilidad", QLabel(self._detail["accounting"]))

    def values(self) -> dict:
        return {}


class PayrollPaymentDialog(HRFormDialog):
    """HR-29: pagar exige método, referencia (si no es efectivo) y confirmar el
    importe; antes «Pagar» usaba efectivo por defecto sin preguntar."""

    dialog_title = "Pagar nómina"

    def __init__(self, detail: dict, parent=None, *, on_submit=None) -> None:
        self._detail = detail
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        totals = self._detail["totals"]
        employees = len(self._detail["employees"].rows)
        self.form.addRow("Importe a pagar", QLabel(money_display(totals["net"])))
        self.form.addRow("Empleados", QLabel(str(employees)))
        self._method = _combo(_PAYMENT_METHODS, empty="Seleccione…")
        self._reference = QLineEdit()
        self._reference.setPlaceholderText("Folio SPEI o número de cheque")
        self._confirm = QLineEdit()
        self._confirm.setPlaceholderText(totals["net"])
        self.form.addRow("Método de pago", self._method)
        self.form.addRow("Referencia", self._reference)
        self.form.addRow("Confirme el importe", self._confirm)

    def _error(self) -> str | None:
        from decimal import Decimal, InvalidOperation
        method = self._method.currentData()
        if not method:
            return "Seleccione el método de pago."
        if method != "CASH" and not self._reference.text().strip():
            return "La transferencia o el cheque requieren su referencia."
        try:
            typed = Decimal(self._confirm.text().replace(",", "").replace("$", "").strip())
        except InvalidOperation:
            return "Escriba el importe a pagar para confirmarlo."
        if typed != Decimal(self._detail["totals"]["net"]):
            return "El importe confirmado no coincide con el neto de la corrida."
        return None

    def values(self) -> dict:
        return {"payment_method": self._method.currentData(),
                "payment_reference": self._reference.text().strip() or None}


class LinkUserDialog(HRFormDialog):
    dialog_title = "Vincular usuario del sistema"

    def __init__(self, user_options, parent=None, *, on_submit=None) -> None:
        self._user_options = user_options
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._user = _combo(self._user_options, empty="Seleccione…")
        note = QLabel("El usuario vinculado registra su asistencia al abrir y cerrar caja.")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        self.form.addRow("Usuario", self._user)
        self.form.addRow(note)

    def _error(self) -> str | None:
        return None if self._user.currentData() else "Seleccione el usuario."

    def values(self) -> dict:
        return {"user_id": self._user.currentData()}


class CatalogDialog(HRFormDialog):
    """Create a department or a position (code + name)."""

    def __init__(self, kind_label: str, parent=None, *, on_submit=None,
                 unit_options=None) -> None:
        self.dialog_title = f"Nuevo {kind_label}"
        #: Departamentos: a qué unidad organizacional pertenecen (vacío = la
        #: sucursal de la sesión). Los puestos no la llevan.
        self._unit_options = unit_options
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._code = QLineEdit()
        self._name = QLineEdit()
        self.form.addRow("Código", self._code)
        self.form.addRow("Nombre", self._name)
        self._unit = None
        if self._unit_options is not None:
            self._unit = _combo(self._unit_options, empty="(Sucursal de la sesión)")
            self.form.addRow("Unidad organizacional", self._unit)

    def _error(self) -> str | None:
        if not self._code.text().strip() or not self._name.text().strip():
            return "El código y el nombre son obligatorios."
        return None

    def values(self) -> dict:
        datos = {"code": self._code.text().strip(), "name": self._name.text().strip()}
        if self._unit is not None:
            datos["org_unit_id"] = self._unit.currentData() or None
        return datos


__all__ = [
    "AdjustmentRequestDialog", "AssignShiftDialog", "CatalogDialog", "EmployeeDialog",
    "GeneratePayrollDialog", "LeaveDialog", "LinkUserDialog", "ManualAttendanceDialog",
    "PayrollDetailDialog", "PayrollPaymentDialog", "ShiftDialog",
]
