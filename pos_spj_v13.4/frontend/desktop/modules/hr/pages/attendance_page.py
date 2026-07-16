"""Asistencia — jornadas del día y ajustes pendientes."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import ManualAttendanceDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import create_primary_button, create_secondary_button


class AttendancePage(HRPage):
    title = "Asistencia"
    subtitle = "Jornadas registradas (caja y registro manual)"
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
        manual_btn = create_primary_button(self, "Registro manual")
        manual_btn.clicked.connect(self._register_manual)
        self.header.add_action(manual_btn)

    def _load(self) -> None:
        self.set_table(self._presenter.workdays())

    def _register_manual(self) -> None:
        options = self._presenter.employee_options()
        if not options:
            self.notify(False, "No hay empleados activos.")
            return
        dialog = ManualAttendanceDialog(options, self)
        if dialog.exec_():
            ok, msg = self._presenter.register_manual_attendance(**dialog.values())
            self.notify(ok, msg)
