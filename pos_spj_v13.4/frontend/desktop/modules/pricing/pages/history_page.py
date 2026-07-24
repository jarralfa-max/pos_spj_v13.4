"""Price/cost change history page (PRC-7) — audit trail of price/cost changes.

UI only: a StandardTable fed by the presenter. No SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class PriceHistoryPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("priceHistoryPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Historial de Precios y Costos",
            subtitle="Bitácora de cambios de precio y costo.",
            icon=getattr(Icons, "AUDIT", None), compact=True)
        layout.addWidget(self.header)

        self.table = StandardTable(columns=[
            ColumnSpec("Fecha", "created_at"),
            ColumnSpec("Producto", "product"),
            ColumnSpec("Campo", "field"),
            ColumnSpec("Anterior", "old_value"),
            ColumnSpec("Nuevo", "new_value"),
            ColumnSpec("Usuario", "user"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        vm = self._presenter.price_history()
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
