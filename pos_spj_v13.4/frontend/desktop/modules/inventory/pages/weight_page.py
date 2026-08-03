"""Weight page (INV-25 / §18) — catch-weight stock on hand.

Presentation-only: lists variable-weight (catch-weight) balances for the branch —
product, warehouse, bucket, pieces, weight and reserved weight. All values come
from the presenter; no SQL, no business logic. Revisiting the section re-reads the
balances.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class WeightPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryWeightPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Peso variable",
            subtitle="Existencias de productos de peso variable (piezas y peso "
                     "capturado).",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Piezas", "numeric"),
            ColumnSpec("Peso", "numeric"),
            ColumnSpec("Peso reservado", "numeric"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.catch_weight()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
