"""Ajustes de asistencia — aprobación con separación de funciones."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_danger_button, create_success_button
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.pages._page_base import HRPage


class AdjustmentsPage(HRPage):
    title = "Ajustes de asistencia"
    subtitle = "Solicitudes de corrección pendientes (se piden desde Asistencia)"
    columns = [
        ColumnSpec("Empleado", "text"),
        ColumnSpec("Jornada", "date"),
        ColumnSpec("Campo", "text"),
        ColumnSpec("Valor previo", "text"),
        ColumnSpec("Valor solicitado", "text"),
        ColumnSpec("Motivo", "text"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        self._add_action(create_success_button(self, "Aprobar"), "attendance_approve",
                         lambda: self._resolve(True))
        self._add_action(create_danger_button(self, "Rechazar"), "attendance_approve",
                         lambda: self._resolve(False))

    def _load(self) -> None:
        self.set_table(self._presenter.pending_adjustments())

    def _resolve(self, approve: bool) -> None:
        adjustment_id = self.selected_id()
        if not adjustment_id:
            self.notify(False, "Seleccione un ajuste.")
            return
        ok, msg = self._presenter.resolve_adjustment(adjustment_id, approve=approve)
        self.notify(ok, msg)
        if ok:
            self.reload()
