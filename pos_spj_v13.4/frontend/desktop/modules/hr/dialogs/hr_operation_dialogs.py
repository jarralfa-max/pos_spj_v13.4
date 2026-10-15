"""Diálogos de nómina avanzada y checador (2026-10-14). Sólo UI: capturan y
delegan al presentador; las reglas viven en los casos de uso."""

from __future__ import annotations

from datetime import date

from PyQt5.QtCore import QDate, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from frontend.desktop.components.buttons import create_danger_button, create_primary_button
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.hr.dialogs._form_dialog import HRFormDialog
from frontend.desktop.modules.hr.dialogs.hr_dialogs import _EmployeePicker

_CONCEPTS = [("BONUS", "Bono"), ("COMMISSION", "Comisión"), ("ADJUSTMENT", "Ajuste a favor")]
_METHODS = [("CASH", "Efectivo"), ("BANK_TRANSFER", "Transferencia"), ("CHECK", "Cheque")]
_KINDS = [("KEYBOARD_READER", "Lector USB (kiosco)"), ("FINGERPRINT", "Huella"),
          ("FACE_RECOGNITION", "Rostro"), ("RFID", "Tarjeta RFID"), ("QR", "Código QR"),
          ("MULTI", "Varios métodos")]
_DRIVERS = [("keyboard", "Kiosco (lector tipo teclado)"),
            ("attlog_file", "Archivo exportado por el checador"),
            ("zkteco", "ZKTeco por red")]
_CREDENTIALS = [("CARD", "Tarjeta"), ("QR", "Código QR"), ("PIN", "PIN"),
                ("DEVICE_USER", "Número de usuario en el checador")]


def _combo(options, *, empty: str | None = None) -> QComboBox:
    combo = QComboBox()
    if empty is not None:
        combo.addItem(empty, None)
    for value, label in options:
        combo.addItem(label, value)
    return combo


def _pydate(edit: QDateEdit) -> date:
    qd = edit.date()
    return date(qd.year(), qd.month(), qd.day())


class PayrollInputDialog(HRFormDialog):
    dialog_title = "Capturar bono, comisión o ajuste"

    def __init__(self, employee_search, parent=None, *, on_submit=None) -> None:
        self._employee_search = employee_search
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._employee = _EmployeePicker(self._employee_search, self)
        self._concept = _combo(_CONCEPTS)
        self._amount = QLineEdit()
        self._amount.setPlaceholderText("0.00")
        self._date = QDateEdit(QDate.currentDate())
        self._date.setCalendarPopup(True)
        self._reason = QLineEdit()
        note = QLabel("Otra persona con permiso debe aprobarlo; la nómina que cubra esa "
                      "fecha lo incluye.")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Concepto", self._concept)
        self.form.addRow("Importe", self._amount)
        self.form.addRow("Fecha a la que corresponde", self._date)
        self.form.addRow("Motivo", self._reason)
        self.form.addRow(note)

    def _error(self) -> str | None:
        if self._employee.current_id() is None:
            return "Seleccione un empleado."
        if not self._amount.text().strip():
            return "Capture el importe."
        if not self._reason.text().strip():
            return "El concepto requiere motivo."
        return None

    def values(self) -> dict:
        return {"employee_id": self._employee.current_id(),
                "concept": self._concept.currentData(),
                "amount": self._amount.text().strip(), "applies_on": _pydate(self._date),
                "reason": self._reason.text().strip()}


class LoanDialog(HRFormDialog):
    dialog_title = "Préstamo o anticipo a empleado"

    def __init__(self, employee_search, parent=None, *, on_submit=None) -> None:
        self._employee_search = employee_search
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._employee = _EmployeePicker(self._employee_search, self)
        self._kind = _combo([("LOAN", "Préstamo"), ("ADVANCE", "Anticipo de sueldo")])
        self._principal = QLineEdit()
        self._principal.setPlaceholderText("Importe entregado")
        self._installment = QLineEdit()
        self._installment.setPlaceholderText("Abono por nómina")
        self._method = _combo(_METHODS, empty="Seleccione…")
        self._reference = QLineEdit()
        self._reference.setPlaceholderText("Folio SPEI o número de cheque")
        self._reason = QLineEdit()
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Tipo", self._kind)
        self.form.addRow("Importe", self._principal)
        self.form.addRow("Abono por nómina", self._installment)
        self.form.addRow("Cómo se entrega", self._method)
        self.form.addRow("Referencia", self._reference)
        self.form.addRow("Motivo", self._reason)

    def _error(self) -> str | None:
        if self._employee.current_id() is None:
            return "Seleccione un empleado."
        if not self._method.currentData():
            return "Seleccione cómo se entrega el dinero."
        if not self._reason.text().strip():
            return "El préstamo requiere motivo."
        return None

    def values(self) -> dict:
        return {"employee_id": self._employee.current_id(), "kind": self._kind.currentData(),
                "principal": self._principal.text().strip(),
                "installment": self._installment.text().strip(),
                "payment_method": self._method.currentData(),
                "payment_reference": self._reference.text().strip() or None,
                "reason": self._reason.text().strip()}


class LeaveBalanceAdjustDialog(HRFormDialog):
    dialog_title = "Ajustar saldo de vacaciones"

    def __init__(self, employee_search, parent=None, *, on_submit=None,
                 balance_text=None) -> None:
        self._employee_search = employee_search
        self._balance_text = balance_text
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._employee = _EmployeePicker(self._employee_search, self)
        self._balance = QLabel("")
        self._balance.setWordWrap(True)
        self._balance.setProperty("role", "muted")
        self._employee.selected.connect(lambda *_: self._balance.setText(
            self._balance_text(self._employee.current_id()) if self._balance_text else ""))
        self._days = QSpinBox()
        self._days.setRange(-60, 60)
        self._reason = QLineEdit()
        self.form.addRow("Empleado", self._employee)
        self.form.addRow("Saldo actual", self._balance)
        self.form.addRow("Días (+ a favor, − en contra)", self._days)
        self.form.addRow("Motivo", self._reason)

    def _error(self) -> str | None:
        if self._employee.current_id() is None:
            return "Seleccione un empleado."
        if self._days.value() == 0:
            return "El ajuste debe ser distinto de cero."
        if not self._reason.text().strip():
            return "El ajuste requiere motivo."
        return None

    def values(self) -> dict:
        return {"employee_id": self._employee.current_id(), "days": self._days.value(),
                "reason": self._reason.text().strip()}


class TimeClockDeviceDialog(HRFormDialog):
    dialog_title = "Nuevo checador"

    def _build_form(self) -> None:
        self._code = QLineEdit()
        self._name = QLineEdit()
        self._kind = _combo(_KINDS)
        self._driver = _combo(_DRIVERS)
        self._host = QLineEdit()
        self._host.setPlaceholderText("IP del checador (ZKTeco)")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(4370)
        self._path = QLineEdit()
        self._path.setPlaceholderText("Ruta del archivo que deja el checador (opcional)")
        self.form.addRow("Código", self._code)
        self.form.addRow("Nombre / ubicación", self._name)
        self.form.addRow("Tipo de lector", self._kind)
        self.form.addRow("Conexión", self._driver)
        self.form.addRow("Dirección IP", self._host)
        self.form.addRow("Puerto", self._port)
        self.form.addRow("Archivo", self._path)

    def _error(self) -> str | None:
        if not self._code.text().strip() or not self._name.text().strip():
            return "El código y el nombre son obligatorios."
        if self._driver.currentData() == "zkteco" and not self._host.text().strip():
            return "Un checador por red requiere su dirección IP."
        return None

    def values(self) -> dict:
        settings: dict = {}
        if self._driver.currentData() == "zkteco":
            settings = {"host": self._host.text().strip(), "port": self._port.value()}
        elif self._path.text().strip():
            settings = {"path": self._path.text().strip()}
        return {"code": self._code.text().strip(), "name": self._name.text().strip(),
                "kind": self._kind.currentData(), "driver": self._driver.currentData(),
                "connection_settings": settings}


class CredentialsDialog(FormDialog):
    """Credenciales de checador de un empleado: alta y baja."""

    def __init__(self, presenter, employee_id: str, parent=None) -> None:
        super().__init__(parent, title="Credenciales de checador")
        self._presenter = presenter
        self._employee_id = employee_id
        self._table = StandardTable([ColumnSpec("Tipo"), ColumnSpec("Credencial"),
                                     ColumnSpec("Checador"), ColumnSpec("Estado")], self)
        self.form.addRow(self._table)
        self._type = _combo(_CREDENTIALS)
        self._value = QLineEdit()
        self._value.setPlaceholderText("Pase la tarjeta/QR por el lector o escriba el dato")
        self._type.currentIndexChanged.connect(self._sync_echo)
        self._device = _combo(presenter.device_options(), empty="Todos los checadores")
        note = QLabel("Las huellas y rostros se registran EN el checador; aquí se da de alta "
                      "el número de usuario que el checador reporta.")
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        self.form.addRow("Tipo", self._type)
        self.form.addRow("Dato", self._value)
        self.form.addRow("Válida en", self._device)
        self.form.addRow(note)
        self._message = QLabel("")
        self._message.setWordWrap(True)
        self.form.addRow(self._message)
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        add = create_primary_button(row, "Dar de alta")
        add.clicked.connect(self._enroll)
        revoke = create_danger_button(row, "Dar de baja la seleccionada")
        revoke.clicked.connect(self._revoke)
        layout.addWidget(add)
        layout.addWidget(revoke)
        layout.addStretch(1)
        self.form.addRow(row)
        self.add_button_box(ok_text="Cerrar")
        self._reload()

    def _sync_echo(self) -> None:
        self._value.setEchoMode(QLineEdit.Password if self._type.currentData() == "PIN"
                                else QLineEdit.Normal)

    def _reload(self) -> None:
        model = self._presenter.credentials(self._employee_id)
        self._table.load_rows(model.rows, row_ids=model.row_ids)

    def _enroll(self) -> None:
        ok, message = self._presenter.enroll_credential(
            self._employee_id, credential_type=self._type.currentData(),
            raw_value=self._value.text(), device_id=self._device.currentData())
        self._message.setText(message)
        if ok:
            self._value.clear()
            self._reload()

    def _revoke(self) -> None:
        credential_id = self._table.selected_row_id()
        if not credential_id:
            self._message.setText("Seleccione una credencial.")
            return
        reason, accepted = FormDialog.get_text(self, "Dar de baja credencial", "Motivo:")
        if accepted:
            ok, message = self._presenter.revoke_credential(credential_id, reason=reason)
            self._message.setText(message)
            if ok:
                self._reload()


class KioskDialog(FormDialog):
    """Modo checador: el lector USB "teclea" la tarjeta/QR y Enter registra la
    marcación; el PIN se teclea oculto. La ventana queda abierta para el siguiente."""

    def __init__(self, presenter, device_id: str, device_label: str, parent=None) -> None:
        super().__init__(parent, title=f"Checador — {device_label}")
        self._presenter = presenter
        self._device_id = device_id
        self._type = _combo(_CREDENTIALS[:3])
        self._input = QLineEdit()
        self._input.setPlaceholderText("Pase su tarjeta o código QR…")
        big = QFont(self._input.font())
        big.setPointSize(max(14, big.pointSize() + 6))
        self._input.setFont(big)
        self._type.currentIndexChanged.connect(self._sync_echo)
        self._input.returnPressed.connect(self._punch)
        self._result = QLabel("")
        self._result.setAlignment(Qt.AlignCenter)
        self._result.setWordWrap(True)
        result_font = QFont(self._result.font())
        result_font.setPointSize(max(14, result_font.pointSize() + 4))
        result_font.setBold(True)
        self._result.setFont(result_font)
        self.form.addRow("Método", self._type)
        self.form.addRow(self._input)
        self.form.addRow(self._result)
        self.add_button_box(ok_text="Cerrar")
        self._input.setFocus()

    def _sync_echo(self) -> None:
        pin = self._type.currentData() == "PIN"
        self._input.setEchoMode(QLineEdit.Password if pin else QLineEdit.Normal)
        self._input.setPlaceholderText("Teclee su PIN y Enter" if pin
                                       else "Pase su tarjeta o código QR…")
        self._input.setFocus()

    def _punch(self) -> None:
        value = self._input.text()
        self._input.clear()
        if not value.strip():
            return
        ok, message = self._presenter.kiosk_punch(
            self._device_id, credential_type=self._type.currentData(), raw_value=value)
        self._result.setProperty("role", "success" if ok else "error")
        self._result.setText(message)
        self._result.style().unpolish(self._result)
        self._result.style().polish(self._result)
        self._input.setFocus()


class CatalogEditDialog(HRFormDialog):
    dialog_title = "Editar catálogo"

    def __init__(self, name: str, parent=None, *, on_submit=None) -> None:
        self._initial = name
        super().__init__(parent, on_submit=on_submit)

    def _build_form(self) -> None:
        self._name = QLineEdit(self._initial)
        self._active = QCheckBox("Activo (se ofrece al capturar empleados)")
        self._active.setChecked(True)
        self.form.addRow("Nombre", self._name)
        self.form.addRow(self._active)

    def _error(self) -> str | None:
        return None if self._name.text().strip() else "El nombre es obligatorio."

    def values(self) -> dict:
        return {"name": self._name.text().strip(), "active": self._active.isChecked()}
