"""Locations page (INV-5) — hierarchical storage locations of a warehouse.

UI only: the presenter returns the location hierarchy already flattened with
indentation, so the table shows the warehouse → zone → aisle → rack tree.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class LocationsPage(QWidget):
    def __init__(self, presenter, warehouse_id=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("locationsPage")
        self._presenter = presenter
        self._warehouse_id = warehouse_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Ubicaciones",
            subtitle="Jerarquía de ubicaciones: pasillo → rack → nivel → posición.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Código", "text"),
            ColumnSpec("Nombre", "text"),
            ColumnSpec("Nivel", "numeric"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self._table)

    def set_warehouse(self, warehouse_id: str) -> None:
        self._warehouse_id = warehouse_id
        self.refresh()

    def refresh(self) -> None:
        if not self._warehouse_id:
            self._table.load_rows([])
            return
        table = self._presenter.location_tree(warehouse_id=self._warehouse_id)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
