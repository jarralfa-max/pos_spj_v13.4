"""Counts page (INV-25 / §17) — recent inventory counts.

Presentation-only: lists recent counts (cyclic, full, spot…) for the branch —
folio, type, warehouse, mode (blind/open) and status. All values come from the
presenter; no SQL, no business logic. Revisiting the section re-reads the counts.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class CountsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryCountsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Conteos",
            subtitle="Conteos cíclicos y físicos, reconteo y varianza.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Modalidad", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Creado", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.counts()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
