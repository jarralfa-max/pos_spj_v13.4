"""Price lists page (PRC-7) — base/channel/customer/promotional lists + status.

UI only: a StandardTable fed by the presenter. No SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class PriceListsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("priceListsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Listas de Precio",
            subtitle="Listas base, de canal, de cliente y promocionales.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        self.table = StandardTable(columns=[
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "kind"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Descuento", "discount"),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        vm = self._presenter.price_lists()
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
