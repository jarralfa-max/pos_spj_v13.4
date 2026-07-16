"""Vacaciones y permisos — solicitud y aprobación."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import LeaveDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import (
    create_danger_button,
    create_primary_button,
    create_success_button,
)


class LeavePage(HRPage):
    title = "Vacaciones y permisos"
    subtitle = "Solicitudes de ausencia y su autorización"
    columns = [
        ColumnSpec("Empleado", "text"),
        ColumnSpec("Tipo", "text"),
        ColumnSpec("Desde", "date"),
        ColumnSpec("Hasta", "date"),
        ColumnSpec("Días", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        new_btn = create_primary_button(self, "Nueva solicitud")
        new_btn.clicked.connect(self._request)
        self.header.add_action(new_btn)
        approve = create_success_button(self, "Aprobar")
        approve.clicked.connect(lambda: self._resolve(True))
        self.header.add_action(approve)
        reject = create_danger_button(self, "Rechazar")
        reject.clicked.connect(lambda: self._resolve(False))
        self.header.add_action(reject)

    def _load(self) -> None:
        self.set_table(self._presenter.leave_requests())

    def _request(self) -> None:
        employees = self._presenter.employee_options()
        if not employees:
            self.notify(False, "No hay empleados activos.")
            return
        dialog = LeaveDialog(employees, self)
        if dialog.exec_():
            ok, msg = self._presenter.request_leave(**dialog.values())
            self.notify(ok, msg)

    def _resolve(self, approve: bool) -> None:
        leave_id = self.selected_id()
        if not leave_id:
            self.notify(False, "Seleccione una solicitud.")
            return
        ok, msg = self._presenter.resolve_leave(leave_id, approve=approve)
        self.notify(ok, msg)
