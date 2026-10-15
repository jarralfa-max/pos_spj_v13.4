"""Empleados — alta, edición, vínculo de usuario, baja y consulta del padrón.

Auditoría RRHH cebf67a: búsqueda y paginación reales (HR-28; antes mostraba
los primeros 100 sin aviso), alta que conserva la captura si el backend la
rechaza (HR-20) y expediente editable con vigencia de salario y vínculo con
el usuario que abre caja (HR-30).
"""

from __future__ import annotations

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import EmployeeDialog, LinkUserDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage


class EmployeesPage(HRPage):
    title = "Empleados"
    subtitle = "Padrón de personal de la sucursal"
    searchable = True
    paginated = True
    columns = [
        ColumnSpec("Código", "text"),
        ColumnSpec("Nombre", "text"),
        ColumnSpec("Departamento", "text"),
        ColumnSpec("Puesto", "text"),
        ColumnSpec("Ingreso", "date"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Nuevo empleado"), "employee_create",
                         self._create)
        self._add_action(create_secondary_button(self, "Editar"), "employee_update",
                         self._edit)
        self._add_action(create_secondary_button(self, "Vincular usuario"), "employee_update",
                         self._link_user)
        self._add_action(create_secondary_button(self, "Credenciales de checador"),
                         "time_clock_manage", self._credentials)
        self._add_action(create_danger_button(self, "Dar de baja"), "employee_deactivate",
                         self._deactivate)

    def _load(self) -> None:
        search = self._search.text().strip() if hasattr(self, "_search") else ""
        self.set_table(self._presenter.employees(
            search=search or None, offset=self._page * self.page_size, limit=self.page_size))

    def _create(self) -> None:
        dialog = EmployeeDialog(self, on_submit=lambda values: self._presenter.create_employee(
            **values), catalogs=self._presenter.catalog_options())
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Empleado creado"))
            self.reload()

    def _edit(self) -> None:
        employee_id = self.selected_id()
        if not employee_id:
            self.notify(False, "Seleccione un empleado.")
            return
        detail = self._presenter.employee_detail(employee_id)
        if detail is None:
            self.notify(False, "El empleado no está al alcance de tu sesión.")
            return
        dialog = EmployeeDialog(
            self, employee=detail, catalogs=self._presenter.catalog_options(),
            on_submit=lambda values: self._presenter.update_employee(employee_id, **values))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Empleado actualizado"))
            self.reload()

    def _link_user(self) -> None:
        employee_id = self.selected_id()
        if not employee_id:
            self.notify(False, "Seleccione un empleado.")
            return
        options = self._presenter.user_options()
        if not options:
            self.notify(False, "No hay usuarios sin vincular.")
            return
        dialog = LinkUserDialog(options, self, on_submit=lambda values: self._presenter.link_user(
            employee_id, values["user_id"]))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Usuario vinculado"))

    def _credentials(self) -> None:
        from frontend.desktop.modules.hr.dialogs.hr_operation_dialogs import CredentialsDialog
        employee_id = self.selected_id()
        if not employee_id:
            self.notify(False, "Seleccione un empleado.")
            return
        CredentialsDialog(self._presenter, employee_id, self).exec_()

    def _deactivate(self) -> None:
        employee_id = self.selected_id()
        if not employee_id:
            self.notify(False, "Seleccione un empleado.")
            return
        reason, ok = FormDialog.get_text(self, "Dar de baja", "Motivo de la baja:")
        if not ok:
            return
        if not reason.strip():
            self.notify(False, "La baja requiere un motivo.")
            return
        done, msg = self._presenter.deactivate_employee(employee_id, reason=reason.strip())
        self.notify(done, msg)
        if done:
            self.reload()
