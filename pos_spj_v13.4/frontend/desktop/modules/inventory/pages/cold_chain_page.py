"""Cold chain page (INV-25 / §21) — open temperature excursions.

Presentation-only: lists open (unresolved) temperature excursions — warehouse,
lot, temperature, range, status and action taken. All values come from the
presenter; no SQL, no business logic. Revisiting the section re-reads.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ColdChainPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryColdChainPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Cadena de frío",
            subtitle="Excursiones de temperatura abiertas y acción tomada.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Temperatura", "text"),
            ColumnSpec("Rango", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Acción", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.cold_chain_excursions()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
