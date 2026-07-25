"""Marcas de producto — gestión del catálogo plano (P1-02).

UI only: una StandardTable de marcas y una barra de acciones (nueva, editar,
activar/desactivar). Toda mutación pasa por el presenter → use cases canónicos.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ProductBrandsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productBrandsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Marcas",
            subtitle="Catálogo de marcas para clasificar el maestro de productos.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        toolbar = QHBoxLayout()
        self.btn_new = QPushButton("Nueva marca")
        self.btn_edit = QPushButton("Editar")
        self.btn_toggle = QPushButton("Activar/Desactivar")
        can_manage = bool(getattr(self._presenter, "can_manage_brands", False))
        for b in (self.btn_new, self.btn_edit, self.btn_toggle):
            b.setEnabled(can_manage)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.btn_new.clicked.connect(lambda: self._open_form(None))
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_toggle.clicked.connect(self._toggle_selected)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Descripción", "description"),
            ColumnSpec("Estado", "estado"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        brands = self._presenter.brand_catalog()
        rows = [[b["code"], b["name"], b.get("description") or "",
                 "Activa" if b.get("active") else "Inactiva"] for b in brands]
        self.table.load_rows(rows, row_ids=[b["id"] for b in brands])

    def _edit_selected(self) -> None:
        brand_id = self.table.selected_row_id()
        if brand_id:
            self._open_form(self._presenter.get_brand(brand_id))

    def _open_form(self, brand) -> None:
        from frontend.desktop.modules.products.dialogs.brand_form_dialog import (
            BrandFormDialog,
        )
        dialog = BrandFormDialog(self._presenter, brand=brand, parent=self)
        if dialog.exec_():
            self.refresh()

    def _toggle_selected(self) -> None:
        brand_id = self.table.selected_row_id()
        if not brand_id:
            return
        row = self._presenter.get_brand(brand_id)
        if row is None:
            return
        self._presenter.set_brand_active(brand_id, not bool(row.get("active")))
        self.refresh()
