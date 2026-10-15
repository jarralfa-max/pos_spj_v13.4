"""Configuración de RRHH — catálogos de departamentos y puestos (con listado)."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_dialogs import CatalogDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage


class SettingsPage(HRPage):
    title = "Configuración"
    subtitle = "Catálogos base de Recursos Humanos"
    columns = [ColumnSpec("Tipo", "text"), ColumnSpec("Código", "text"),
               ColumnSpec("Nombre", "text")]
    empty_message = "Aún no hay departamentos ni puestos"

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Nuevo departamento"), "settings_manage",
                         self._create_department)
        self._add_action(create_secondary_button(self, "Nuevo puesto"), "settings_manage",
                         self._create_position)
        self._add_action(create_secondary_button(self, "Editar"), "settings_manage",
                         self._edit)

    def _load(self) -> None:
        self.set_table(self._presenter.catalog_table())

    def _edit(self) -> None:
        from frontend.desktop.modules.hr.dialogs.hr_operation_dialogs import CatalogEditDialog
        item_id = self.selected_id()
        if not item_id:
            self.notify(False, "Seleccione un departamento o puesto.")
            return
        kind = self._presenter.catalog_kind(item_id)
        row = self._table.currentRow()
        current = self._table.item(row, 2).text() if row >= 0 and self._table.item(row, 2) else ""
        dialog = CatalogEditDialog(current, self, on_submit=lambda v: self._presenter.update_catalog_item(
            item_id, kind=kind, name=v["name"], active=v["active"]))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Catálogo actualizado"))
            self.reload()

    def _create_department(self) -> None:
        dialog = CatalogDialog("departamento", self,
                               on_submit=lambda v: self._presenter.create_department(**v))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Departamento creado"))
            self.reload()

    def _create_position(self) -> None:
        dialog = CatalogDialog("puesto", self,
                               on_submit=lambda v: self._presenter.create_position(**v))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Puesto creado"))
            self.reload()
