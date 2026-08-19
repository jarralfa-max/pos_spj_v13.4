"""CustomerPanel (POS-19) — structural equivalent of the legacy
`group_cliente` (search/assign/quick-create/loyalty display,
`docs/refactor/sales_pos_layout_inventory.md` §1), backed by SALES-10's real
`SalesCustomerClient`-driven use cases instead of freehand dialog fields.

The real `CustomerSearchBox` component already exists (`frontend/desktop/
components/customer_search_box.py`) — reused here rather than a bespoke
search widget, wired to `SalesPosPresenter.search_customers()`.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from frontend.desktop.components import CustomerSearchBox, create_secondary_button
from frontend.desktop.themes.tokens import Spacing


class CustomerPanel(QFrame):
    customer_selected = pyqtSignal(str)  # customer_id

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posClientFrame")
        self._presenter = presenter

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        root.setSpacing(Spacing.XS)

        title = QLabel("Cliente", self)
        title.setObjectName("posClientSectionLabel")
        root.addWidget(title)

        self._search = CustomerSearchBox(self, provider=self._search_provider)
        self._search.selected.connect(self._on_selected)
        root.addWidget(self._search)

        info_row = QHBoxLayout()
        self._display = QLabel("Público en general", self)
        info_row.addWidget(self._display)
        info_row.addStretch(1)
        self._btn_quick_create = create_secondary_button(self, "+ Nuevo")
        info_row.addWidget(self._btn_quick_create)
        root.addLayout(info_row)

        self._loyalty = QLabel("", self)
        self._loyalty.setVisible(False)
        root.addWidget(self._loyalty)

    def set_customer(self, name: str | None, *, loyalty_points: int | None = None) -> None:
        self._display.setText(name or "Público en general")
        if loyalty_points is not None:
            self._loyalty.setText(f"⭐ {loyalty_points} puntos")
            self._loyalty.setVisible(True)
        else:
            self._loyalty.setVisible(False)

    def quick_create_button(self):
        return self._btn_quick_create

    def _search_provider(self, query: str):
        from frontend.desktop.components.search_selector import SearchOption

        if not query:
            return []
        return [
            SearchOption(id=result.id, label=result.display_name, subtitle=result.phone_e164 or "")
            for result in self._presenter.search_customers(query)
        ]

    def _on_selected(self, option) -> None:
        self.customer_selected.emit(option.id)
