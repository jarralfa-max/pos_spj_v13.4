"""Adjustments page (INV-25 / §14) — recent inventory adjustments.

Presentation-only: lists recent adjustments for the branch — folio, reason,
warehouse and status. All values come from the presenter; no SQL, no business
logic. Revisiting the section re-reads the adjustments.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class AdjustmentsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAdjustmentsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Ajustes",
            subtitle="Ajustes con motivo, autorización y posteo.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Motivo", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Creado", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.adjustments()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
