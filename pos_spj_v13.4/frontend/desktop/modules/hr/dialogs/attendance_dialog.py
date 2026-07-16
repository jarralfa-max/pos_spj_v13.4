"""Dialog for manual HR attendance registration."""

from __future__ import annotations

from datetime import datetime

from PyQt5.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QTextEdit, QVBoxLayout

from frontend.desktop.modules.hr.hr_view_models import HRAttendanceFormViewModel


class HRAttendanceDialog(QDialog):
    """Captures manual attendance data; persistence is delegated to the presenter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Registrar asistencia")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._employee_id = QLineEdit(self)
        self._branch_id = QLineEdit(self)
        self._occurred_at = QLineEdit(datetime.now().replace(microsecond=0).isoformat(), self)
        self._punch_type = QComboBox(self)
        self._punch_type.addItems(["ENTRY", "EXIT"])
        self._reason = QLineEdit(self)
        self._notes = QTextEdit(self)
        form.addRow("Empleado", self._employee_id)
        form.addRow("Sucursal", self._branch_id)
        form.addRow("Fecha y hora ISO", self._occurred_at)
        form.addRow("Tipo", self._punch_type)
        form.addRow("Motivo", self._reason)
        form.addRow("Observaciones", self._notes)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def form_value(self) -> HRAttendanceFormViewModel:
        return HRAttendanceFormViewModel(
            employee_id=self._employee_id.text().strip(),
            branch_id=self._branch_id.text().strip(),
            occurred_at=self._occurred_at.text().strip(),
            punch_type=self._punch_type.currentText(),
            reason=self._reason.text().strip(),
            notes=self._notes.toPlainText().strip() or None,
        )
