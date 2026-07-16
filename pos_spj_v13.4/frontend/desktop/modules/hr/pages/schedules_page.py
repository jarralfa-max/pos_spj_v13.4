"""Turnos — catálogo de turnos y asignación a empleados."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import AssignShiftDialog, ShiftDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import create_primary_button, create_secondary_button


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
        new_btn = create_primary_button(self, "Nuevo turno")
        new_btn.clicked.connect(self._create_shift)
        self.header.add_action(new_btn)
        assign_btn = create_secondary_button(self, "Asignar turno")
        assign_btn.clicked.connect(self._assign_shift)
        self.header.add_action(assign_btn)

    def _load(self) -> None:
        self.set_table(self._presenter.shifts())

    def _create_shift(self) -> None:
        dialog = ShiftDialog(self)
        if dialog.exec_():
            ok, msg = self._presenter.create_shift(**dialog.values())
            self.notify(ok, msg)

    def _assign_shift(self) -> None:
        employees = self._presenter.employee_options()
        shifts = self._presenter.shift_options()
        if not employees or not shifts:
            self.notify(False, "Se requieren empleados activos y al menos un turno.")
            return
        dialog = AssignShiftDialog(employees, shifts, self)
        if dialog.exec_():
            ok, msg = self._presenter.assign_shift(**dialog.values())
            self.notify(ok, msg)
