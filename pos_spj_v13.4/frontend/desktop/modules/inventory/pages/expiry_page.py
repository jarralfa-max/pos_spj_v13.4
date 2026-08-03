"""Expiry page (INV-25 / §9.4) — lots at risk of expiration.

Presentation-only: lists available lots classified as expired / critical / near
expiry (nearest first), with product, lot, quantity, days-to-expiry and risk. All
values come from the presenter; no SQL, no business logic. Revisiting re-reads.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ExpiryPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryExpiryPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Caducidades",
            subtitle="Lotes en riesgo de caducidad: vencidos, críticos y próximos.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Días", "numeric"),
            ColumnSpec("Riesgo", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.expiring()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
