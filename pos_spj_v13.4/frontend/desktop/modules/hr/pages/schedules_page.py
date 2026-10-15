"""Turnos — catálogo de turnos y asignación a empleados."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import AssignShiftDialog, ShiftDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage


class SchedulesPage(HRPage):
    title = "Turnos"
    subtitle = "Definición de turnos y asignación de horarios"
    columns = [
        ColumnSpec("Turno", "text"),
        ColumnSpec("Inicio", "date"),
        ColumnSpec("Fin", "date"),
        ColumnSpec("Descanso", "numeric"),
        ColumnSpec("Tolerancia", "numeric"),
    ]

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Nuevo turno"), "shift_manage",
                         self._create_shift)
        self._add_action(create_secondary_button(self, "Asignar turno"), "shift_manage",
                         self._assign_shift)

    def _load(self) -> None:
        self.set_table(self._presenter.shifts())

    def _create_shift(self) -> None:
        dialog = ShiftDialog(self, on_submit=lambda values: self._presenter.create_shift(**values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Turno creado"))
            self.reload()

    def _assign_shift(self) -> None:
        shifts = self._presenter.shift_options()
        if not shifts:
            self.notify(False, "Se requiere al menos un turno.")
            return
        dialog = AssignShiftDialog(
            self._presenter.search_employees, shifts, self,
            on_submit=lambda values: self._presenter.assign_shift(**values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Turno asignado"))
