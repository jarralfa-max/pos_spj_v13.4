"""Traceability page (INV-25 / §46) — upstream trace of a lot.

Presentation-only: a ``SearchInput`` picks/scans a lot id and the page lists the
movement events that fed it (date, movement, direction, module, document) — the
lot's origin chain. All values come from the presenter; no SQL, no business logic.
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


class TraceabilityPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryTraceabilityPage")
        self._presenter = presenter
        self._lot_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Trazabilidad",
            subtitle="Rastreo ascendente de un lote: eventos que lo originaron.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._search = SearchInput(placeholder="Lote (ID o código escaneado)…")
        self._search.search_submitted.connect(self._on_search)
        layout.addWidget(self._search)

        self._table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"),
            ColumnSpec("Movimiento", "text"),
            ColumnSpec("Dirección", "text"),
            ColumnSpec("Módulo", "text"),
            ColumnSpec("Documento", "text"),
        ])
        layout.addWidget(self._table)

    def _on_search(self, text: str) -> None:
        self._lot_id = str(text or "").strip()
        self.refresh()

    def refresh(self) -> None:
        table = self._presenter.traceability(lot_id=self._lot_id)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
