"""Movimientos bancarios registrados (depósitos, retiros, comisiones e intereses)."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class TreasuryMovementsPage(FinancePage):
    title = "Movimientos de tesorería"
    subtitle = "Cada movimiento con su contrapartida y su asiento"
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Referencia"),
        ColumnSpec("Contrapartida"),
        ColumnSpec("Asiento", "date"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.treasury_movements())
