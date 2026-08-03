"""Lots page (INV-25 / §46) — a product's lots by FEFO.

Presentation-only: a ``SearchInput`` picks/scans a product (no huge combo) and the
page lists its lots — code, origin, quality status and expiration — ordered by
earliest expiry. All values come from the presenter; no SQL, no business logic.
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


class LotsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryLotsPage")
        self._presenter = presenter
        self._product_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Lotes",
            subtitle="Lotes por producto: origen, estado de calidad y caducidad (FEFO).",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._search = SearchInput(placeholder="Producto (ID o código escaneado)…")
        self._search.search_submitted.connect(self._on_search)
        layout.addWidget(self._search)

        self._table = StandardTable(columns=[
            ColumnSpec("Lote", "text"),
            ColumnSpec("Origen", "text"),
            ColumnSpec("Calidad", "status"),
            ColumnSpec("Caducidad", "text"),
        ])
        layout.addWidget(self._table)

    def _on_search(self, text: str) -> None:
        self._product_id = str(text or "").strip()
        self.refresh()

    def refresh(self) -> None:
        table = self._presenter.lots(product_id=self._product_id)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
