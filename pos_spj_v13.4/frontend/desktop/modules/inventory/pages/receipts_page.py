"""Receipts page (INV-25 / §15) — recent inbound receipts into inventory.

Presentation-only: lists recent receipt movements (purchase, transfer, production)
for the branch — date, type, source module, document and status. All values come
from the presenter; no SQL, no business logic. Revisiting the section re-reads the
ledger.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ReceiptsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryReceiptsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Recepciones",
            subtitle="Entradas de mercancía al inventario (compra, transferencia, "
                     "producción).",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Módulo", "text"),
            ColumnSpec("Documento", "text"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.receipts()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
