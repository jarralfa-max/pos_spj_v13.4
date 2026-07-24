"""Product prices page (PRC-7) — sale price by product / branch / list.

UI only: a SearchInput feeding the presenter and a StandardTable of prices. No SQL,
no business logic; the presenter formats money.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchInput,
    StandardTable,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ProductPricesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productPricesPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Precios por Producto",
            subtitle="Precio de venta por producto, sucursal y lista; precio mínimo.",
            icon=getattr(Icons, "PRICE", None), compact=True)
        layout.addWidget(self.header)

        self.search = SearchInput(placeholder="Buscar producto por nombre o código…")
        self.search.textChanged.connect(self._on_search)
        layout.addWidget(self.search)

        self.table = StandardTable(columns=[
            ColumnSpec("Producto", "product"),
            ColumnSpec("Lista", "list"),
            ColumnSpec("Sucursal", "branch"),
            ColumnSpec("Precio", "sale_price"),
            ColumnSpec("Mínimo", "min_price"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def _on_search(self, text) -> None:
        self.refresh(query=text)

    def refresh(self, *, query=None) -> None:
        vm = self._presenter.product_prices(query=query)
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
