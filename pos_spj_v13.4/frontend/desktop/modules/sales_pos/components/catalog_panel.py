"""CatalogPanel — panel izquierdo: búsqueda y escáner, categorías, cuadrícula.

Toda lectura pasa por `SalesPosPresenter.catalog_search()`/`categories()`
(§14). La búsqueda en vivo usa el debounce de `SearchInput`; Enter (lo que
manda un lector de código de barras) se enruta como escaneo por
`ScanCodeRouter` (§17).

Re-auditoría POS (2026-10-01): el filtro de categorías mandaba el NOMBRE y la
consulta filtra por ID, así que elegir una categoría vaciaba la cuadrícula.
Ahora el combo lleva el id. Se agregó el indicador de estado del escáner del
contrato visual (§1: "Estado del scanner").
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout, QWidget

from frontend.desktop.components import SearchInput, StatusBadge, create_secondary_button
from frontend.desktop.modules.sales_pos.components.product_grid import ProductGrid
from frontend.desktop.themes.tokens import Spacing


class CatalogPanel(QWidget):
    product_selected = pyqtSignal(object)  # ProductCatalogEntryDTO
    code_scanned = pyqtSignal(str)  # código escaneado / enviado con Enter

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCatalogPanel")
        self._presenter = presenter

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        root.setSpacing(Spacing.SM)

        search_row = QHBoxLayout()
        self._search = SearchInput(self, placeholder="Buscar producto, código o código de barras...")
        self._search.search_changed.connect(self._on_search_changed)
        self._search.search_submitted.connect(self._on_search_submitted)
        search_row.addWidget(self._search, stretch=1)

        # Auditoría V09: no se afirma "listo" sin haber leído nada — un lector
        # es un teclado y no hay forma de detectarlo antes de su primera lectura.
        self._scanner = StatusBadge("Escáner: esperando lectura", self, status="neutral")
        self._scanner.setToolTip("Escanea el código de un producto o la tarjeta de un cliente "
                                 "con el cursor en la búsqueda.")
        filters = QHBoxLayout()
        filters.addWidget(self._scanner)

        self._category = QComboBox(self)
        self._category.setObjectName("posCategoryFilter")
        self._category.addItem("Todas las categorías", None)
        self._category.currentIndexChanged.connect(self._on_search_changed)
        filters.addWidget(self._category)
        root.addLayout(search_row)
        root.addLayout(filters)

        self._grid = ProductGrid(self)
        self._grid.product_selected.connect(self.product_selected)
        root.addWidget(self._grid, stretch=1)

        # Auditoría V08: el catálogo llega por páginas; el resto, a petición.
        self._page = 0
        self._more = create_secondary_button(self, "Mostrar más productos")
        self._more.setObjectName("posCatalogMore")
        self._more.clicked.connect(self.load_more)
        self._more.setVisible(False)
        root.addWidget(self._more)

    @property
    def grid(self) -> ProductGrid:
        return self._grid

    def load_categories(self) -> None:
        for category_id, name in self._presenter.categories():
            self._category.addItem(name, category_id)

    def _fetch(self, page: int):
        fetch = getattr(self._presenter, "catalog_page", None)
        if not callable(fetch):
            return self._presenter.catalog_search(
                search=self._search.query(), category_id=self._category.currentData()), False
        return fetch(search=self._search.query(), category_id=self._category.currentData(),
                     page=page)

    def refresh(self) -> None:
        self._page = 0
        products, more = self._fetch(0)
        self._grid.set_products(products)
        self._more.setVisible(more)

    def load_more(self) -> None:
        self._page += 1
        products, more = self._fetch(self._page)
        self._grid.append_products(products)
        self._more.setVisible(more)

    def clear_search(self) -> None:
        self._search.clear_search()

    def focus_search(self) -> None:
        self._search.setFocus()

    def set_scanner_status(self, text: str, status: str) -> None:
        self._scanner.setText(text)
        self._scanner.set_status(status)

    def _on_search_changed(self, *_args) -> None:
        self.refresh()

    def _on_search_submitted(self, text: str) -> None:
        code = text.strip()
        if code:
            self.code_scanned.emit(code)
