"""Activos fijos y depreciación."""

from __future__ import annotations

from datetime import date

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button


class FixedAssetsPage(FinancePage):
    title = "Activos fijos"
    subtitle = "Registro, depreciación y baja"
    columns = [
        ColumnSpec("Activo"),
        ColumnSpec("Costo", "numeric"),
        ColumnSpec("Depreciación acumulada", "numeric"),
        ColumnSpec("Valor en libros", "numeric"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Último periodo", "date"),
    ]

    def _build_actions(self) -> None:
        depreciate_btn = create_primary_button(self, "Correr depreciación del mes")
        depreciate_btn.clicked.connect(self._depreciate)
        self.header.add_action(depreciate_btn)

    def _depreciate(self) -> None:
        today = date.today()
        self.notify(*self._presenter.run_depreciation(today.year, today.month))

    def _load(self) -> None:
        self.set_table(self._presenter.fixed_assets())
