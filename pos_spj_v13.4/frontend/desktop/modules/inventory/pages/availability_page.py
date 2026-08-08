"""Availability page (INV-25 / §9.3) — per-product availability breakdown.

Presentation-only: an ``EntitySearchInput`` resolves the product by name, code
or barcode against the canonical catalog (§P0-D — never a hand-typed UUID),
and the page shows its availability broken down by physical bucket — what
Sales can promise vs. why the rest is not available (reserved, quarantined,
quality-blocked, damaged, expired…). All values come from the presenter; no
SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class AvailabilityPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAvailabilityPage")
        self._presenter = presenter
        self._product_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Disponibilidad",
            subtitle="Disponible para prometer y desglose por bucket físico.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._search = EntitySearchInput(
            self, provider=self._presenter.product_options,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self._search.selected.connect(self._on_product_selected)
        layout.addWidget(self._search)

        self._table = StandardTable(columns=[
            ColumnSpec("Concepto", "text"),
            ColumnSpec("Cantidad", "numeric"),
        ])
        layout.addWidget(self._table)

    def _on_product_selected(self, product_id) -> None:
        self._product_id = str(product_id or "")
        self.refresh()

    def refresh(self) -> None:
        table = self._presenter.availability_breakdown(product_id=self._product_id)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
