"""Quarantine page (INV-25 / §31) — open quarantines.

Presentation-only: lists open quarantines (product, lot, reason, quantity,
status) for the branch. All values come from the presenter; no SQL, no business
logic. Revisiting the section re-reads the quarantines.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class QuarantinePage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryQuarantinePage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Cuarentena",
            subtitle="Cuarentenas abiertas: bloqueo, revisión y liberación de lotes.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Motivo", "text"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.quarantines()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
