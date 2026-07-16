"""Configuración de RRHH — catálogos de departamentos y puestos."""

from __future__ import annotations

from frontend.desktop.modules.hr.dialogs.hr_dialogs import CatalogDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage
from modulos.ui_components import create_primary_button, create_secondary_button


class SettingsPage(HRPage):
    title = "Configuración"
    subtitle = "Catálogos base de Recursos Humanos"

    def _build_actions(self) -> None:
        dept = create_primary_button(self, "Nuevo departamento")
        dept.clicked.connect(self._create_department)
        self.header.add_action(dept)
        position = create_secondary_button(self, "Nuevo puesto")
        position.clicked.connect(self._create_position)
        self.header.add_action(position)

    def _load(self) -> None:  # catalogs are managed via dialogs
        return

    def _create_department(self) -> None:
        dialog = CatalogDialog("departamento", self)
        if dialog.exec_():
            ok, msg = self._presenter.create_department(**dialog.values())
            self.notify(ok, msg)

    def _create_position(self) -> None:
        dialog = CatalogDialog("puesto", self)
        if dialog.exec_():
            ok, msg = self._presenter.create_position(**dialog.values())
            self.notify(ok, msg)
