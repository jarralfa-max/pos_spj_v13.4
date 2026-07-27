"""Capital y CAPEX."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button


class CapitalPage(FinancePage):
    title = "Capital"
    subtitle = "Aportaciones y origen de fondos"
    columns = [
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Saldo contable", "numeric"),
        ColumnSpec("Moneda", "status"),
    ]

    def _build_actions(self) -> None:
        contribution_btn = create_primary_button(self, "Registrar aportación")
        contribution_btn.clicked.connect(self._contribute)
        self.header.add_action(contribution_btn)

    def _contribute(self) -> None:
        from frontend.desktop.modules.finance.dialogs.capital_contribution_dialog import (
            CapitalContributionDialog,
        )
        dialog = CapitalContributionDialog(self, self._presenter.treasury_accounts())
        if dialog.exec_():
            data = dialog.data()
            self.notify(*self._presenter.register_capital_contribution(**data))

    def _load(self) -> None:
        self.set_table(self._presenter.treasury_position())
