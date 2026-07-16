"""Ajustes de asistencia — aprobación con separación de funciones."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import create_danger_button, create_success_button


class AdjustmentsPage(HRPage):
    title = "Ajustes de asistencia"
    subtitle = "Solicitudes de corrección pendientes de aprobación"
    columns = [
        ColumnSpec("Empleado", "text"),
        ColumnSpec("Campo", "text"),
        ColumnSpec("Valor previo", "text"),
        ColumnSpec("Valor solicitado", "text"),
        ColumnSpec("Motivo", "text"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        approve = create_success_button(self, "Aprobar")
        approve.clicked.connect(lambda: self._resolve(True))
        self.header.add_action(approve)
        reject = create_danger_button(self, "Rechazar")
        reject.clicked.connect(lambda: self._resolve(False))
        self.header.add_action(reject)

    def _load(self) -> None:
        self.set_table(self._presenter.pending_adjustments())

    def _resolve(self, approve: bool) -> None:
        adjustment_id = self.selected_id()
        if not adjustment_id:
            self.notify(False, "Seleccione un ajuste.")
            return
        ok, msg = self._presenter.resolve_adjustment(adjustment_id, approve=approve)
        self.notify(ok, msg)
