"""Costs page (PRC-7) — average / last / standard cost per product.

UI only: a StandardTable fed by the presenter. No SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class CostsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pricingCostsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Costos",
            subtitle="Costo promedio, último y estándar por producto.",
            icon=getattr(Icons, "COST", None), compact=True)
        layout.addWidget(self.header)

        self.table = StandardTable(columns=[
            ColumnSpec("Producto", "product"),
            ColumnSpec("Promedio", "average_cost"),
            ColumnSpec("Último", "last_cost"),
            ColumnSpec("Estándar", "standard_cost"),
            ColumnSpec("Método", "cost_method"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        vm = self._presenter.costs()
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
