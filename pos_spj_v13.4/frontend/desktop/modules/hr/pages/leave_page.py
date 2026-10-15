"""Vacaciones y permisos — solicitud, aprobación y cancelación controlada."""

from __future__ import annotations

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import LeaveDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage


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
        self._add_action(create_primary_button(self, "Nueva solicitud"), "leave_request",
                         self._request)
        self._add_action(create_success_button(self, "Aprobar"), "leave_approve",
                         lambda: self._resolve(True))
        self._add_action(create_danger_button(self, "Rechazar"), "leave_approve",
                         lambda: self._resolve(False))
        self._add_action(create_secondary_button(self, "Cancelar solicitud"), "leave_request",
                         self._cancel)
        self._add_action(create_secondary_button(self, "Ajustar saldo"), "leave_balance_adjust",
                         self._adjust_balance)

    def _load(self) -> None:
        self.set_table(self._presenter.leave_requests())

    def _request(self) -> None:
        dialog = LeaveDialog(
            self._presenter.search_employees, self,
            on_submit=lambda values: self._presenter.request_leave(**values),
            balance_text=self._presenter.vacation_balance_text)
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Solicitud registrada"))
            self.reload()

    def _resolve(self, approve: bool) -> None:
        leave_id = self.selected_id()
        if not leave_id:
            self.notify(False, "Seleccione una solicitud.")
            return
        ok, msg = self._presenter.resolve_leave(leave_id, approve=approve)
        self.notify(ok, msg)
        if ok:
            self.reload()

    def _adjust_balance(self) -> None:
        from frontend.desktop.modules.hr.dialogs.hr_operation_dialogs import (
            LeaveBalanceAdjustDialog,
        )
        dialog = LeaveBalanceAdjustDialog(
            self._presenter.search_employees, self,
            on_submit=lambda v: self._presenter.adjust_leave_balance(
                v["employee_id"], days=v["days"], reason=v["reason"]),
            balance_text=self._presenter.vacation_balance_text)
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Saldo ajustado"))

    def _cancel(self) -> None:
        leave_id = self.selected_id()
        if not leave_id:
            self.notify(False, "Seleccione una solicitud.")
            return
        reason, ok = FormDialog.get_text(self, "Cancelar solicitud",
                                         "Motivo (obligatorio si ya estaba aprobada):")
        if not ok:
            return
        done, msg = self._presenter.cancel_leave(leave_id, reason=reason.strip() or None)
        self.notify(done, msg)
        if done:
            self.reload()
