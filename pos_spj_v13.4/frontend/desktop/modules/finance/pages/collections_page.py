"""Cobros registrados (auditoría de CxC)."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class CollectionsPage(FinancePage):
    title = "Cobros"
    subtitle = "Cobranza aplicada a cuentas por cobrar"
    columns = [
        ColumnSpec("Documento", "date"),
        ColumnSpec("Cliente", "date"),
        ColumnSpec("Emisión", "date"),
        ColumnSpec("Vencimiento", "date"),
        ColumnSpec("Original", "numeric"),
        ColumnSpec("Saldo", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.open_receivables())
