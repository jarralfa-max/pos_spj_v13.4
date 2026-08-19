"""ProductGrid (POS-19) — renders `ProductCatalogEntryDTO` rows (SALES-7's
`SalesCatalogQueryService`) as clickable cards. Structural equivalent of the
legacy `modulos/ventas.py::ProductCard` grid, but stock badges come from the
DTO's own already-resolved `stock_state` (SALES-7's real fix: the legacy
grid computed stock classification itself in the widget, exactly the
anti-pattern §16 forbids) — this component never classifies stock itself.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget

from frontend.desktop.components import StatusBadge
from frontend.desktop.components.cards import SummaryCard
from frontend.desktop.themes.tokens import Spacing

_STATE_VARIANT = {
    "AVAILABLE": "success", "LOW_STOCK": "warning", "CRITICAL_STOCK": "warning",
    "OUT_OF_STOCK": "danger", "NOT_SELLABLE": "danger",
}
_COLUMNS = 4


class ProductGrid(QScrollArea):
    product_selected = pyqtSignal(str)  # product_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posProductGrid")
        self.setWidgetResizable(True)

        self._container = QWidget(self)
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(Spacing.SM)
        self.setWidget(self._container)
        self._cards: list[SummaryCard] = []

    def set_products(self, products) -> None:
        for card in self._cards:
            card.setParent(None)
        self._cards.clear()

        for index, product in enumerate(products):
            card = self._build_card(product)
            row, col = divmod(index, _COLUMNS)
            self._grid.addWidget(card, row, col)
            self._cards.append(card)

    def _build_card(self, product) -> SummaryCard:
        card = SummaryCard(self._container)
        card.setObjectName("posProductCard")
        card.setProperty("sellable", product.sellable)

        name = QLabel(product.name, card)
        name.setWordWrap(True)
        card.add(name)

        price = QLabel(f"${product.effective_price:.2f}", card)
        price.setObjectName("posProductPrice")
        card.add(price)

        badge = StatusBadge(
            product.stock_state.replace("_", " ").title(), card,
            status=_STATE_VARIANT.get(product.stock_state, "neutral"))
        card.add(badge)

        if product.sellable:
            card.mousePressEvent = lambda _event, pid=product.product_id: (
                self.product_selected.emit(pid))
        return card
