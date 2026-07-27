"""Dialog for manual HR attendance registration."""

from __future__ import annotations

from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import QDateTimeEdit, QDialogButtonBox, QLineEdit, QTextEdit

from frontend.desktop.components import FormField, SearchableComboBox, StandardDialog, StandardForm
from frontend.desktop.modules.hr.hr_view_models import HRAttendanceFormViewModel


class HRAttendanceDialog(StandardDialog):
    """Captures manual attendance data; persistence is delegated to the presenter."""

    def __init__(self, parent=None) -> None:
        self._form = StandardForm(parent)
        self._employee_id = QLineEdit(parent)
        self._branch_id = QLineEdit(parent)
        self._occurred_at = QDateTimeEdit(parent)
        self._occurred_at.setObjectName("dateTimeInput")
        self._occurred_at.setCalendarPopup(True)
        self._occurred_at.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._occurred_at.setDateTime(QDateTime.currentDateTime())
        self._punch_type = SearchableComboBox(parent, placeholder="Selecciona tipo…")
        self._punch_type.set_options((("ENTRY", "Entrada"), ("EXIT", "Salida")))
        self._reason = QLineEdit(parent)
        self._notes = QTextEdit(parent)
        self._notes.setObjectName("standardTextArea")
        self._build_form()
        super().__init__(
            parent,
            title="Registrar asistencia",
            description="Registra una entrada o salida manual con motivo auditable.",
            content=self._form,
            buttons=QDialogButtonBox.Save | QDialogButtonBox.Cancel,
        )
        self.set_initial_focus(self._employee_id)

    def accept(self) -> None:
        if not self._validate():
            self._form.focus_first_error()
            return
        super().accept()

    def form_value(self) -> HRAttendanceFormViewModel:
        occurred_at = self._occurred_at.dateTime().toPyDateTime().replace(microsecond=0).isoformat()
        return HRAttendanceFormViewModel(
            employee_id=self._employee_id.text().strip(),
            branch_id=self._branch_id.text().strip(),
            occurred_at=occurred_at,
            punch_type=self._punch_type.selected_id() or "",
            reason=self._reason.text().strip(),
            notes=self._notes.toPlainText().strip() or None,
        )

    def _build_form(self) -> None:
        self._form.add_field("employee", FormField("Empleado", self._employee_id, helper_text="UUID del empleado hasta conectar EntitySearchInput.", required=True))
        self._form.add_field("branch", FormField("Sucursal", self._branch_id, helper_text="UUID de sucursal hasta conectar BranchSearchBox.", required=True))
        self._form.add_field("occurred_at", FormField("Fecha y hora", self._occurred_at, helper_text="Fecha y hora local del registro manual.", required=True))
        self._form.add_field("punch_type", FormField("Tipo", self._punch_type, required=True))
        self._form.add_field("reason", FormField("Motivo", self._reason, helper_text="Explica por qué la marcación se registra manualmente.", required=True))
        self._form.add_field("notes", FormField("Observaciones", self._notes, helper_text="Notas opcionales para auditoría."))

    def _validate(self) -> bool:
        self._form.clear_errors()
        if not self._employee_id.text().strip():
            self._form.set_error("employee", "Captura o selecciona un empleado válido.")
        if not self._branch_id.text().strip():
            self._form.set_error("branch", "Captura una sucursal válida.")
        if self._punch_type.selected_id() is None:
            self._form.set_error("punch_type", "Selecciona si la marcación es entrada o salida.")
        if not self._reason.text().strip():
            self._form.set_error("reason", "Captura un motivo para la marcación manual.")
        return not self._form.has_errors()
