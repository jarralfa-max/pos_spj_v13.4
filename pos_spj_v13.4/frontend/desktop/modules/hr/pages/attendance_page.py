"""Asistencia — jornadas, registro manual y solicitud de ajuste."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import (
    AdjustmentRequestDialog,
    ManualAttendanceDialog,
)
from frontend.desktop.modules.hr.pages._page_base import HRPage


class AttendancePage(HRPage):
    title = "Asistencia"
    subtitle = "Jornadas registradas (caja y registro manual), en hora de la sucursal"
    columns = [
        ColumnSpec("Empleado", "text"),
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Entrada", "date"),
        ColumnSpec("Salida", "date"),
        ColumnSpec("Trabajado", "numeric"),
        ColumnSpec("Retardo", "numeric"),
        ColumnSpec("Extra", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Registro manual"), "attendance_manual",
                         self._register_manual)
        self._add_action(create_secondary_button(self, "Solicitar ajuste"), "attendance_adjust",
                         self._request_adjustment)

    def _load(self) -> None:
        self.set_table(self._presenter.workdays())
        pending = self._presenter.pending_cash_events()
        if pending:
            self.notify(False, f"{pending} apertura(s)/cierre(s) de caja esperan que el "
                               "usuario se vincule con su empleado (Empleados → Vincular usuario).")

    def _register_manual(self) -> None:
        dialog = ManualAttendanceDialog(
            self._presenter.search_employees, self,
            on_submit=lambda values: self._presenter.register_manual_attendance(**values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Marcación registrada"))
            self.reload()

    def _request_adjustment(self) -> None:
        workday_id = self.selected_id()
        if not workday_id:
            self.notify(False, "Seleccione la jornada a corregir.")
            return
        workday = self._presenter.workday_detail(workday_id)
        if workday is None:
            self.notify(False, "La jornada no está al alcance de tu sesión.")
            return
        dialog = AdjustmentRequestDialog(
            workday, self,
            on_submit=lambda values: self._presenter.request_adjustment(**values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Ajuste solicitado"))
