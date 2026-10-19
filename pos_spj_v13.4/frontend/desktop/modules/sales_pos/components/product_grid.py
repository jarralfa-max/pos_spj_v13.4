"""ProductGrid — tarjetas del catálogo del POS (§16).

Cada tarjeta presenta lo que `SalesCatalogQueryService` ya resolvió (§16: "No
calcular el estado en el widget"): nombre, código, precio por unidad,
existencia y estado. El estado se TRADUCE aquí, no se clasifica.

Re-auditoría POS (2026-10-01), medido con captura sobre la base real: las
tarjetas decían "Out Of Stock"/"Available" en inglés, no mostraban código ni
unidad ni existencia, y una tarjeta no vendible simplemente no respondía al
clic — "no pasa nada" es feedback invisible. Ahora toda tarjeta emite el clic
y la pantalla explica por qué un producto no se puede agregar (sin precio, no
vendible). El número de columnas se adapta al ancho del panel.

PROD-21: la tarjeta muestra la imagen principal del producto
(`ProductCatalogEntryDTO.image_reference`, que el catálogo ya traía y nadie
dibujaba). Sin imagen, o con el archivo ausente, muestra las iniciales: todas
las tarjetas conservan la misma altura.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget

from frontend.desktop.components import StatusBadge, apply_tooltip
from frontend.desktop.components.cards import SummaryCard, InteractiveSummaryCard
from frontend.desktop.components.image_thumbnail import ImageThumbnail
from frontend.desktop.modules.sales_pos.components.cart_table import format_quantity
from frontend.desktop.themes.tokens import CardMetrics, Spacing

STATE_LABELS = {
    "AVAILABLE": "Disponible",
    "LOW_STOCK": "Existencia baja",
    "CRITICAL_STOCK": "Existencia crítica",
    "OUT_OF_STOCK": "Sin existencia",
    "NOT_SELLABLE": "No vendible",
}
_STATE_VARIANT = {
    "AVAILABLE": "success", "LOW_STOCK": "warning", "CRITICAL_STOCK": "danger",
    "OUT_OF_STOCK": "danger", "NOT_SELLABLE": "danger",
}
#: Tarjeta del contrato visual (`sales_pos_layout_inventory.md`: 175 px) y
#: su hueco con la separación de la cuadrícula.
CARD_WIDTH = 175
CARD_SLOT_WIDTH = 185
MIN_COLUMNS = 2
#: Área de imagen del contrato visual (175×85) dentro del margen de la tarjeta.
THUMBNAIL_WIDTH = CARD_WIDTH - 2 * CardMetrics.PADDING_MD
THUMBNAIL_HEIGHT = 85


class ProductGrid(QScrollArea):
    product_selected = pyqtSignal(object)  # ProductCatalogEntryDTO

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posProductGrid")
        self.setWidgetResizable(True)

        self._container = QWidget(self)
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(Spacing.SM)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setWidget(self._container)
        self._cards: list[SummaryCard] = []
        self._columns = 4

        self._empty = QLabel("No hay productos que coincidan.", self._container)
        self._empty.setProperty("role", "empty")
        self._empty.setVisible(False)

    def columns(self) -> int:
        return self._columns

    def set_products(self, products) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        products = list(products)
        self._empty.setVisible(not products)
        self._grid.removeWidget(self._empty)
        if not products:
            self._grid.addWidget(self._empty, 0, 0)
        for product in products:
            self._cards.append(self._build_card(product))
        self._layout_cards()

    def append_products(self, products) -> None:
        """La página siguiente se AGREGA: las tarjetas ya dibujadas no se
        reconstruyen (auditoría V08)."""
        start = len(self._cards)
        for product in products:
            self._cards.append(self._build_card(product))
        for index in range(start, len(self._cards)):
            row, col = divmod(index, self._columns)
            self._grid.addWidget(self._cards[index], row, col)

    def card_count(self) -> int:
        return len(self._cards)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        columns = max(MIN_COLUMNS, self.viewport().width() // CARD_SLOT_WIDTH)
        if columns != self._columns:
            self._columns = columns
            self._layout_cards()

    def _layout_cards(self) -> None:
        for index, card in enumerate(self._cards):
            row, col = divmod(index, self._columns)
            self._grid.addWidget(card, row, col)

    def _build_card(self, product) -> SummaryCard:
        card = InteractiveSummaryCard(self._container)
        card.setObjectName("posProductCard")
        card.setProperty("sellable", product.sellable)
        card.setAccessibleName(product.name)
        card.setCursor(Qt.PointingHandCursor)
        card.setFixedWidth(CARD_WIDTH)

        thumbnail = ImageThumbnail(card, width=THUMBNAIL_WIDTH, height=THUMBNAIL_HEIGHT)
        thumbnail.setObjectName("posProductImage")
        thumbnail.set_image(product.image_reference, placeholder=product.name,
                            accessible_name=f"Imagen de {product.name}")
        card.add(thumbnail)

        name = QLabel(product.name, card)
        name.setWordWrap(True)
        name.setProperty("role", "sectionTitle")
        card.add(name)

        if product.sku:
            code = QLabel(product.sku, card)
            code.setProperty("role", "muted")
            card.add(code)

        unidad = product.unit or ""
        if product.priced:
            price_text = f"${product.effective_price:,.2f}" + (f" / {unidad}" if unidad else "")
        else:
            price_text = "Sin precio"
        price = QLabel(price_text, card)
        price.setObjectName("posProductPrice")
        card.add(price)

        stock = QLabel(f"Existencia: {format_quantity(product.available_quantity)} {unidad}".strip(),
                       card)
        stock.setProperty("role", "muted")
        card.add(stock)

        state = product.stock_state if product.priced else "NOT_SELLABLE"
        badge = StatusBadge(
            "Sin precio" if not product.priced else STATE_LABELS.get(state, state), card,
            status=_STATE_VARIANT.get(state, "neutral"))
        card.add(badge)

        if product.warnings:
            apply_tooltip(card, "\n".join(product.warnings))

        card.activated.connect(lambda p=product, c=card: self._activate(c, p))
        return card

    def _activate(self, selected, product):
        for card in self._cards:
            card.set_selected(card is selected)
        self.product_selected.emit(product)
