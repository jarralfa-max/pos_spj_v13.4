"""CatalogPanel (POS-19/POS-20) — left panel: search + category filter +
product grid. Structural equivalent of the legacy `panel_izquierdo`
(search_row + category_row + product grid, see `docs/refactor/
sales_pos_layout_inventory.md` §1), rebuilt to delegate every read to
`SalesPosPresenter.catalog_search()`/`categories()` (SALES-7) instead of
the legacy grid's own direct queries.

POS-20 "Validar scanner": a physical barcode scanner behaves like a very
fast typist followed by Enter/CR — exactly `SearchInput`'s own
`search_submitted` signal (fires on Return, distinct from the debounced
`search_changed` used for live-as-you-type browsing). Emitting `code_scanned`
here lets the workspace route that submission through `ScanCodeRouter`
(SALES-12, `presenter.scan_code()`) — the real, previously-unwired
consumer of that use case; live-typed browsing keeps filtering the grid as
before, never touching the scan router.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from frontend.desktop.components import SearchInput
from frontend.desktop.modules.sales_pos.components.product_grid import ProductGrid
from frontend.desktop.themes.tokens import Spacing


class CatalogPanel(QWidget):
    product_selected = pyqtSignal(str)  # product_id
    code_scanned = pyqtSignal(str)  # raw scanned/submitted code

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCatalogPanel")
        self._presenter = presenter

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        root.setSpacing(Spacing.SM)

        search_row = QHBoxLayout()
        self._search = SearchInput(self, placeholder="Buscar producto o código de barras...")
        self._search.search_changed.connect(self._on_search_changed)
        self._search.search_submitted.connect(self._on_search_submitted)
        search_row.addWidget(self._search, stretch=1)

        self._category = QComboBox(self)
        self._category.setObjectName("posCategoryFilter")
        self._category.addItem("Todas las categorías", None)
        self._category.currentIndexChanged.connect(self._on_search_changed)
        search_row.addWidget(self._category)
        root.addLayout(search_row)

        self._grid = ProductGrid(self)
        self._grid.product_selected.connect(self.product_selected)
        root.addWidget(self._grid, stretch=1)

    def load_categories(self) -> None:
        for name in self._presenter.categories():
            self._category.addItem(name, name)

    def refresh(self) -> None:
        category = self._category.currentData()
        products = self._presenter.catalog_search(
            search=self._search.query(), category_id=category)
        self._grid.set_products(products)

    def clear_search(self) -> None:
        self._search.clear_search()

    def _on_search_changed(self, *_args) -> None:
        self.refresh()

    def _on_search_submitted(self, text: str) -> None:
        code = text.strip()
        if code:
            self.code_scanned.emit(code)
