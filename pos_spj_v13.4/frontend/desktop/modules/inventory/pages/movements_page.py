"""Movements page (INV-25 / §15) — recent ledger movements.

Presentation-only: lists the most recent posted movements (date, type, source
module/document, status) for the branch. All values come from the presenter; no
SQL, no business logic. Revisiting the section re-reads the ledger.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class MovementsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryMovementsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Movimientos",
            subtitle="Ledger de movimientos: entradas, salidas y transferencias.",
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
        table = self._presenter.movements()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
