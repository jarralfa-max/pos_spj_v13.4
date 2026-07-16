"""Concrete HR form dialogs. Pure UI: capture input, no business rules."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from PyQt5.QtCore import QDate, QTime
from PyQt5.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDateTimeEdit,
    QLineEdit,
    QSpinBox,
    QTimeEdit,
)

from frontend.desktop.modules.hr.dialogs._form_dialog import HRFormDialog
from frontend.desktop.modules.hr.hr_view_models import LEAVE_TYPE_ES

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


def _combo(options: list[tuple]) -> QComboBox:
    combo = QComboBox()
    for value, label in options:
        combo.addItem(label, value)
    return combo


class EmployeeDialog(HRFormDialog):
    dialog_title = "Nuevo empleado"

    def _build_form(self) -> None:
        self._code = QLineEdit()
        self._first = QLineEdit()
        self._last = QLineEdit()
        self._contract = _combo(_CONTRACT_TYPES)
        self._frequency = _combo(_FREQUENCIES)
        self._base = QLineEdit()
        self._base.setPlaceholderText("0.00")
        self._daily = QLineEdit()
        self._daily.setPlaceholderText("0.00")
        self._hire = QDateEdit(QDate.currentDate())
        self._hire.setCalendarPopup(True)
        self._phone = QLineEdit()
        self._phone.setPlaceholderText("+52...")
        self._email = QLineEdit()
        self.form.addRow("Código", self._code)
        self.form.addRow("Nombre", self._first)
        self.form.addRow("Apellidos", self._last)
        self.form.addRow("Contrato", self._contract)
        self.form.addRow("Frecuencia de pago", self._frequency)
        self.form.addRow("Sueldo base", self._base)
        self.form.addRow("Sueldo diario", self._daily)
        self.form.addRow("Fecha de ingreso", self._hire)
        self.form.addRow("Teléfono", self._phone)
        self.form.addRow("Correo", self._email)

    def _error(self) -> str | None:
        if not self._code.text().strip():
            return "El código es obligatorio."
        if not self._first.text().strip() or not self._last.text().strip():
            return "El nombre y los apellidos son obligatorios."
        for field, label in ((self._base, "sueldo base"), (self._daily, "sueldo diario")):
            try:
                if float(field.text() or 0) < 0:
                    return f"El {label} no puede ser negativo."
            except ValueError:
                return f"El {label} debe ser numérico."
        return None

    def values(self) -> dict:
        qd = self._hire.date()
        return {
            "employee_code": self._code.text().strip(),
            "first_name": self._first.text().strip(),
            "last_name": self._last.text().strip(),
            "contract_type": self._contract.currentData(),
            "payment_frequency": self._frequency.currentData(),
            "base_salary": self._base.text().strip() or "0.00",
            "daily_salary": self._daily.text().strip() or "0.00",
            "hire_date": date(qd.year(), qd.month(), qd.day()),
            "phone_e164": self._phone.text().strip() or None,
            "email": self._email.text().strip() or None,
        }


class ManualAttendanceDialog(HRFormDialog):
    dialog_title = "Registro manual de asistencia"

    def __init__(self, employee_options: list[tuple[str, str]], parent=None) -> None:
        self._employee_options = employee_options
        super().__init__(parent)

    def _build_form(self) -> None:
        self._employee = _combo(self._employee_options)
        self._punch = _combo([("ENTRY", "Entrada"), ("EXIT", "Salida")])
        self._when = QDateTimeEdit(datetime.now())
        self._when.setCalendarPopup(True)
        self._when.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._reason = QLineEdit()
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Tipo", self._punch)
        self.form.addRow("Fecha y hora", self._when)
        self.form.addRow("Motivo", self._reason)

    def _error(self) -> str | None:
        if self._employee.currentData() is None:
            return "Seleccione un empleado."
        if not self._reason.text().strip():
            return "El registro manual requiere un motivo."
        return None

    def values(self) -> dict:
        qdt = self._when.dateTime().toPyDateTime().replace(tzinfo=timezone.utc)
        return {
            "employee_id": self._employee.currentData(),
            "punch_type": self._punch.currentData(),
            "occurred_at": qdt,
            "reason": self._reason.text().strip(),
        }


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
        self.form.addRow("Descanso (min)", self._break)
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

    def __init__(self, employee_options, shift_options, parent=None) -> None:
        self._employee_options = employee_options
        self._shift_options = shift_options
        super().__init__(parent)

    def _build_form(self) -> None:
        from PyQt5.QtWidgets import QCheckBox, QWidget, QHBoxLayout
        self._employee = _combo(self._employee_options)
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
        if self._employee.currentData() is None:
            return "Seleccione un empleado."
        if self._shift.currentData() is None:
            return "Seleccione un turno."
        if not any(check.isChecked() for _, check in self._weekday_checks):
            return "Seleccione al menos un día."
        return None

    def values(self) -> dict:
        qd = self._from.date()
        weekdays = tuple(value for value, check in self._weekday_checks if check.isChecked())
        return {
            "employee_id": self._employee.currentData(),
            "work_shift_id": self._shift.currentData(),
            "effective_from": date(qd.year(), qd.month(), qd.day()),
            "weekdays": weekdays,
        }


class LeaveDialog(HRFormDialog):
    dialog_title = "Nueva solicitud"

    def __init__(self, employee_options, parent=None) -> None:
        self._employee_options = employee_options
        super().__init__(parent)

    def _build_form(self) -> None:
        self._employee = _combo(self._employee_options)
        self._type = _combo([(k, v) for k, v in LEAVE_TYPE_ES.items()
                             if k in ("VACATION", "PAID_LEAVE", "UNPAID_LEAVE", "SICK_LEAVE")])
        self._start = QDateEdit(QDate.currentDate())
        self._start.setCalendarPopup(True)
        self._end = QDateEdit(QDate.currentDate())
        self._end.setCalendarPopup(True)
        self._reason = QLineEdit()
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Tipo", self._type)
        self.form.addRow("Desde", self._start)
        self.form.addRow("Hasta", self._end)
        self.form.addRow("Motivo", self._reason)

    def _error(self) -> str | None:
        if self._employee.currentData() is None:
            return "Seleccione un empleado."
        if self._end.date() < self._start.date():
            return "La fecha final no puede ser anterior a la inicial."
        return None

    def values(self) -> dict:
        qs, qe = self._start.date(), self._end.date()
        return {
            "employee_id": self._employee.currentData(),
            "leave_type": self._type.currentData(),
            "start_date": date(qs.year(), qs.month(), qs.day()),
            "end_date": date(qe.year(), qe.month(), qe.day()),
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
        qs, qe = self._start.date(), self._end.date()
        return {
            "period_start": date(qs.year(), qs.month(), qs.day()),
            "period_end": date(qe.year(), qe.month(), qe.day()),
        }


class CatalogDialog(HRFormDialog):
    """Create a department or a position (code + name)."""

    def __init__(self, kind_label: str, parent=None) -> None:
        self.dialog_title = f"Nuevo {kind_label}"
        super().__init__(parent)

    def _build_form(self) -> None:
        self._code = QLineEdit()
        self._name = QLineEdit()
        self.form.addRow("Código", self._code)
        self.form.addRow("Nombre", self._name)

    def _error(self) -> str | None:
        if not self._code.text().strip() or not self._name.text().strip():
            return "El código y el nombre son obligatorios."
        return None

    def values(self) -> dict:
        return {"code": self._code.text().strip(), "name": self._name.text().strip()}
