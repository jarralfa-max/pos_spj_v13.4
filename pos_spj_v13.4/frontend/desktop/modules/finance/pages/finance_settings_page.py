"""Configuración financiera — perfiles contables (solo lectura aquí)."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class FinanceSettingsPage(FinancePage):
    title = "Configuración"
    subtitle = "Perfiles contables vigentes (los cambios no reexpresan asientos pasados)"
    columns = [
        ColumnSpec("Perfil", "date"),
        ColumnSpec("Descripción"),
        ColumnSpec("Instrumento", "status"),
        ColumnSpec("Vigente desde", "date"),
        ColumnSpec("Vigente hasta", "date"),
        ColumnSpec("Estado", "status"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.posting_profiles())
