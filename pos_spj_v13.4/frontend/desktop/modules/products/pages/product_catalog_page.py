"""Product catalog page (§42, §43) — searchable master catalog.

UI only: a SearchInput feeding the presenter, and a StandardTable of products.
No SQL, no business logic, no local styles; the presenter formats rows.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

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

        toolbar = QHBoxLayout()
        self.search = SearchInput(placeholder="Buscar producto por nombre o código…")
        self.search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search, 1)
        self.btn_new = QPushButton("Nuevo")
        self.btn_edit = QPushButton("Editar")
        self.btn_new.clicked.connect(lambda: self._open_form(None))
        self.btn_edit.clicked.connect(self._edit_selected)
        can_write = getattr(self._presenter, "can_write", False)
        for b in (self.btn_new, self.btn_edit):
            b.setEnabled(can_write)
            toolbar.addWidget(b)
        layout.addLayout(toolbar)

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

    def _edit_selected(self) -> None:
        product_id = self.table.selected_row_id()
        if product_id:
            self._open_form(product_id)

    def _open_form(self, product_id) -> None:
        from frontend.desktop.modules.products.dialogs.product_form_dialog import (
            ProductFormDialog,
        )
        dialog = ProductFormDialog(self._presenter, product_id=product_id, parent=self)
        if dialog.exec_():
            self.refresh(query=self.search.text() or None)

    def refresh(self, *, query=None) -> None:
        table = self._presenter.catalog(query=query)
        self.table.load_rows(table.rows, row_ids=table.row_ids)
