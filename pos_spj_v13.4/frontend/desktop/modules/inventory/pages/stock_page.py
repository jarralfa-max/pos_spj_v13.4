"""Stock page (INV-25 / §14) — physical on-hand stock.

Presentation-only: lists on-hand balances (quantity ≠ 0) per product, warehouse
and physical bucket for the branch. All values come from the presenter; no SQL,
no business logic. Revisiting the section re-reads the balances.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class StockPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryStockPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Existencias",
            subtitle="Existencia física por producto, almacén y bucket.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Reservado", "numeric"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.stock()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
