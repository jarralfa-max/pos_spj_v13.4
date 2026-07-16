"""Empleados — alta, baja y consulta del padrón."""

from __future__ import annotations

from PyQt5.QtWidgets import QInputDialog

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import EmployeeDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import create_danger_button, create_primary_button


class EmployeesPage(HRPage):
    title = "Empleados"
    subtitle = "Padrón de personal por sucursal"
    columns = [
        ColumnSpec("Código", "text"),
        ColumnSpec("Nombre", "text"),
        ColumnSpec("Departamento", "text"),
        ColumnSpec("Puesto", "text"),
        ColumnSpec("Ingreso", "date"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        new_btn = create_primary_button(self, "Nuevo empleado")
        new_btn.clicked.connect(self._create)
        self.header.add_action(new_btn)
        off_btn = create_danger_button(self, "Dar de baja")
        off_btn.clicked.connect(self._deactivate)
        self.header.add_action(off_btn)

    def _load(self) -> None:
        self.set_table(self._presenter.employees())

    def _create(self) -> None:
        dialog = EmployeeDialog(self)
        if dialog.exec_():
            ok, msg = self._presenter.create_employee(**dialog.values())
            self.notify(ok, msg)

    def _deactivate(self) -> None:
        employee_id = self.selected_id()
        if not employee_id:
            self.notify(False, "Seleccione un empleado.")
            return
        reason, ok = QInputDialog.getText(self, "Dar de baja", "Motivo de la baja:")
        if not ok:
            return
        if not reason.strip():
            self.notify(False, "La baja requiere un motivo.")
            return
        done, msg = self._presenter.deactivate_employee(employee_id, reason=reason.strip())
        self.notify(done, msg)
