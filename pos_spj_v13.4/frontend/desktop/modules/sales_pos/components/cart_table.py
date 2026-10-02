"""CartTable — las líneas de la venta (proyección de `SaleDTO.lines`, §12).

Estructura del contrato visual (`sales_pos_layout_inventory.md` §1): encabezado
"CARRITO DE COMPRA" con el botón de vaciar, la tabla, y el estado vacío.

Re-auditoría POS (2026-10-01): el carrito sólo se podía MIRAR. Los casos de uso
de cambiar cantidad y quitar línea existían y no tenían ningún llamador en la
pantalla: un producto agregado por error obligaba a cancelar la venta entera.
Ahora la línea seleccionada se puede corregir ("Cantidad / peso") o quitar
("Quitar", tecla Supr) desde el encabezado del carrito; la tabla sólo emite la intención, el presentador la
ejecuta.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QShortcut, QStackedWidget, QVBoxLayout, QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    IconProvider,
    Icons,
    StandardTable,
    create_ghost_button,
)
from frontend.desktop.themes.tokens import Spacing

#: Anchos de un panel de 380-600 px: el producto absorbe el sobrante y el
#: Total nunca queda fuera de la vista (con los 160 px por omisión de la tabla
#: estándar, Precio y Total quedaban detrás de una barra horizontal). El
#: descuento es lo primero que se oculta si no cabe.
_COLUMNS = (
    ColumnSpec("Producto", "text", min_width=90, preferred_width=110, stretch=True),
    ColumnSpec("Cant.", "numeric", min_width=56, preferred_width=60, stretch=False),
    ColumnSpec("Ud.", "text", min_width=40, preferred_width=44, stretch=False),
    ColumnSpec("Precio", "numeric", min_width=64, preferred_width=70, stretch=False),
    ColumnSpec("Desc.", "numeric", min_width=56, preferred_width=60, stretch=False,
               priority=1),
    ColumnSpec("Total", "numeric", min_width=72, preferred_width=80, stretch=False),
)


_EMPTY_TEXT = "El carrito está vacío.\nBusca o escanea un producto."


def format_quantity(value: Decimal) -> str:
    """1.250 kg se lee "1.250"; 2 piezas se lee "2", no "2.000"."""
    value = Decimal(str(value))
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1")))
    return f"{value:.3f}"


class CartTable(QWidget):
    line_selected = pyqtSignal(str)          # line_id
    quantity_requested = pyqtSignal(str)     # line_id
    remove_requested = pyqtSignal(str)       # line_id
    clear_requested = pyqtSignal()

    def __init__(self, parent=None, *, can_edit: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("posCartGroup")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setObjectName("posCartHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.SM, Spacing.XS)
        title = QLabel("CARRITO DE COMPRA", header)
        title.setObjectName("posCartHeaderTitle")
        title.setProperty("role", "sectionTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)
        # Las acciones de la línea viven en el encabezado: a 1366x768 una fila
        # propia le quitaba al carrito el alto de casi dos renglones.
        self.btn_quantity = create_ghost_button(
            header, "Cantidad / peso", tooltip="Corregir la cantidad o el peso de la línea "
            "seleccionada (doble clic en la línea)")
        IconProvider.bind(self.btn_quantity, Icons.EDIT)
        self.btn_quantity.clicked.connect(lambda: self._emit_for_selected(
            self.quantity_requested))
        header_row.addWidget(self.btn_quantity)
        self.btn_remove = create_ghost_button(
            header, "Quitar (Supr)", tooltip="Quitar la línea seleccionada (tecla Supr)")
        IconProvider.bind(self.btn_remove, Icons.CLOSE)
        self.btn_remove.clicked.connect(lambda: self._emit_for_selected(self.remove_requested))
        header_row.addWidget(self.btn_remove)
        self.btn_clear = create_ghost_button(
            header, "Vaciar", tooltip="Cancelar la venta en curso (pide motivo)")
        self.btn_clear.setObjectName("posCartIconBtn")
        IconProvider.bind(self.btn_clear, Icons.DELETE)
        self.btn_clear.clicked.connect(self.clear_requested)
        header_row.addWidget(self.btn_clear)
        root.addWidget(header)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, stretch=1)

        self._table = StandardTable(list(_COLUMNS), self)
        self._table.setObjectName("posCartTable")
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemDoubleClicked.connect(lambda _item: self._emit_for_selected(
            self.quantity_requested))
        self._stack.addWidget(self._table)

        self._empty_label = QLabel("El carrito está vacío.\nBusca o escanea un producto.", self)
        self._empty_label.setObjectName("posCartEmpty")
        self._empty_label.setProperty("role", "empty")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._stack.addWidget(self._empty_label)

        self._remove_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self._table,
                                          activated=lambda: self._emit_for_selected(
                                              self.remove_requested))
        self._can_edit = can_edit
        self._refresh_line_actions()

    def set_lines(self, lines) -> None:
        if not lines:
            self._stack.setCurrentWidget(self._empty_label)
            self._table.setRowCount(0)
            self.btn_clear.setEnabled(False)
            self._refresh_line_actions()
            return
        self._stack.setCurrentWidget(self._table)
        rows = [
            [line.product_snapshot.get("name") or line.product_id,
             format_quantity(line.quantity), line.quantity_unit,
             f"${line.unit_price:,.2f}", f"${line.discount_total:,.2f}",
             f"${line.line_total:,.2f}"]
            for line in lines
        ]
        self._table.load_rows(rows, row_ids=[line.id for line in lines])
        self.btn_clear.setEnabled(True)
        self._refresh_line_actions()

    def set_empty_message(self, text: str | None) -> None:
        """Aviso en el lugar del carrito vacío (p. ej. por qué no se pudo
        abrir la venta), sin un diálogo modal que interrumpa la pantalla."""
        self._empty_label.setText(text or _EMPTY_TEXT)

    def selected_line_id(self) -> str | None:
        return self._table.selected_row_id()

    def select_line(self, line_id: str) -> None:
        for row in range(self._table.rowCount()):
            self._table.selectRow(row)
            if self._table.selected_row_id() == line_id:
                return
        self._table.clearSelection()

    def _emit_for_selected(self, signal) -> None:
        line_id = self.selected_line_id()
        if line_id and self._can_edit:
            signal.emit(line_id)

    def _refresh_line_actions(self) -> None:
        has_selection = bool(self.selected_line_id()) and self._can_edit
        self.btn_quantity.setEnabled(has_selection)
        self.btn_remove.setEnabled(has_selection)

    def _on_selection_changed(self) -> None:
        self._refresh_line_actions()
        line_id = self._table.selected_row_id()
        if line_id:
            self.line_selected.emit(line_id)
