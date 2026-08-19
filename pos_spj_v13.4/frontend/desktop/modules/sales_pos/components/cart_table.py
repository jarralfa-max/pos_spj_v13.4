"""CartTable (POS-19) — the sale's line items. Structural equivalent of the
legacy `modulos/ventas.py::tabla_compra` (7 columns, hidden-when-empty +
`_lbl_cart_empty` shown state — `docs/refactor/sales_pos_layout_inventory.md`
§1), backed by `SaleLineDTO` (SALES-6/8) instead of the legacy's own dict
rows.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLabel, QStackedWidget, QWidget, QVBoxLayout

from frontend.desktop.components import ColumnSpec, StandardTable

_COLUMNS = (
    ColumnSpec("Producto", "text"),
    ColumnSpec("Cantidad", "numeric"),
    ColumnSpec("Unidad", "text"),
    ColumnSpec("Precio", "numeric"),
    ColumnSpec("Descuento", "numeric"),
    ColumnSpec("Total", "numeric"),
)


class CartTable(QWidget):
    line_selected = pyqtSignal(str)  # line_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posCartGroup")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        self._table = StandardTable(list(_COLUMNS), self)
        self._table.setObjectName("posCartTable")
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._stack.addWidget(self._table)

        self._empty_label = QLabel("El carrito está vacío", self)
        self._empty_label.setObjectName("posCartEmpty")
        self._stack.addWidget(self._empty_label)

    def set_lines(self, lines) -> None:
        if not lines:
            self._stack.setCurrentWidget(self._empty_label)
            self._table.setRowCount(0)
            return
        self._stack.setCurrentWidget(self._table)
        rows = [
            [line.product_snapshot.get("name") or line.product_id, str(line.quantity),
             line.quantity_unit, f"{line.unit_price:.2f}", f"{line.discount_total:.2f}",
             f"{line.line_total:.2f}"]
            for line in lines
        ]
        self._table.load_rows(rows, row_ids=[line.id for line in lines])

    def selected_line_id(self) -> str | None:
        return self._table.selected_row_id()

    def _on_selection_changed(self) -> None:
        line_id = self._table.selected_row_id()
        if line_id:
            self.line_selected.emit(line_id)
