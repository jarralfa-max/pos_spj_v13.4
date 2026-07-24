"""Product catalog page (§42, §43) — searchable master catalog.

UI only: a SearchInput feeding the presenter, and a StandardTable of products.
No SQL, no business logic, no local styles; the presenter formats rows.
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


class ProductCatalogPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productCatalogPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Catálogo de Productos",
            subtitle="Maestro de productos con búsqueda por nombre o código.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        self.search = SearchInput(placeholder="Buscar producto por nombre o código…")
        self.search.textChanged.connect(self._on_search)
        layout.addWidget(self.search)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "product_type"),
            ColumnSpec("Estado", "lifecycle_status"),
            ColumnSpec("Cárnico", "is_meat"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def _on_search(self, text) -> None:
        self.refresh(query=text)

    def refresh(self, *, query=None) -> None:
        table = self._presenter.catalog(query=query)
        self.table.load_rows(table.rows, row_ids=table.row_ids)
