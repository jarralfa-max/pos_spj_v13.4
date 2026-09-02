"""Documental purchase-history page (PUR-13 step 2c) — migrated from the monolith's
"Historial de Compras" tab. UI only; reads via the presenter."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_COLUMNS = [
    ColumnSpec("Folio", "text"), ColumnSpec("Proveedor", "text"),
    ColumnSpec("Estado", "status"), ColumnSpec("Fecha", "text"),
]


class PurchaseHistoryPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("purchaseHistoryPage")
        self._presenter = presenter
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        self.header = PageHeader(
            title="Historial de Compras",
            subtitle="Recepciones y documentos de compra registrados.",
            icon=Icons.PURCHASES, compact=True)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        layout.addWidget(self.header)

        self._table = StandardTable(_COLUMNS, self)
        layout.addWidget(self._table, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()
            self._loaded = True

    def reload(self) -> None:
        try:
            model = self._presenter.purchase_history()
            self._table.load_rows(model.rows, row_ids=model.row_ids)
        except Exception as exc:
            QMessageBox.warning(self, "Historial de Compras", f"No fue posible cargar:\n{exc}")
