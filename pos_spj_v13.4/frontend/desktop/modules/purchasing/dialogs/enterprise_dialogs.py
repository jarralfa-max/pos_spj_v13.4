"""Dialogs for the enterprise procurement UI: requisition, order, invoice capture,
goods receipt, and a generic reason prompt. UI only — no business logic."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    FormDialog,
    SearchableComboBox,
    StandardLineEdit,
    StandardTable,
    StandardTextArea,
    create_secondary_button,
)

_PURCHASE_TYPES = [
    ("INVENTORY", "Inventario"), ("RAW_MATERIAL", "Materia prima"), ("POULTRY", "Pollo"),
    ("GROCERY", "Abarrotes"), ("PACKAGING", "Empaque"), ("SUPPLIES", "Insumos"),
    ("SERVICE", "Servicio"), ("EXPENSE", "Gasto"), ("ASSET", "Activo"),
    ("MAINTENANCE", "Mantenimiento"),
]
_PRIORITIES = [("LOW", "Baja"), ("NORMAL", "Normal"), ("HIGH", "Alta"), ("URGENT", "Urgente")]


class _LinesEditor(QWidget):
    """A compact product-lines editor producing list[dict]. With or without price."""

    def __init__(self, parent=None, *, with_price: bool = False) -> None:
        super().__init__(parent)
        self._with_price = with_price
        self._lines: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        self._product = StandardLineEdit(self)
        self._product.setPlaceholderText("Producto (código/ID)")
        self._qty = DecimalInput(self, precision=3, minimum="0")
        self._qty.setPlaceholderText("Cantidad")
        row.addWidget(self._product, stretch=2)
        row.addWidget(self._qty, stretch=1)
        if with_price:
            self._price = DecimalInput(self, precision=2, minimum="0")
            self._price.setPlaceholderText("Precio")
            row.addWidget(self._price, stretch=1)
        add = create_secondary_button(self, "Agregar")
        add.clicked.connect(self._add)
        row.addWidget(add)
        layout.addLayout(row)

        cols = [ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text")]
        if with_price:
            cols.append(ColumnSpec("Precio", "text"))
        self._table = StandardTable(cols, self)
        layout.addWidget(self._table)

    def _add(self) -> None:
        product = self._product.text().strip()
        qty = self._qty.decimal_value()
        if not product or qty is None or qty <= 0:
            return
        line = {"product_id": product, "quantity": str(qty)}
        display = [product, str(qty)]
        if self._with_price:
            price = self._price.decimal_value()
            if price is None:
                return
            line["unit_price"] = str(price)
            line["estimated_unit_cost"] = str(price)
            display.append(str(price))
        self._lines.append(line)
        self._table.load_rows([[*l_disp] for l_disp in self._display_rows()],
                              row_ids=[str(i) for i in range(len(self._lines))])
        self._product.clear()
        self._qty.clear()
        if self._with_price:
            self._price.clear()

    def _display_rows(self) -> list[list[str]]:
        rows = []
        for ln in self._lines:
            row = [ln["product_id"], ln["quantity"]]
            if self._with_price:
                row.append(ln.get("unit_price", ""))
            rows.append(row)
        return rows

    def lines(self) -> list[dict]:
        return list(self._lines)


class RequisitionFormDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva solicitud de compra")
        self._branch = StandardLineEdit(self)
        self._branch.setPlaceholderText("Sucursal")
        self._type = SearchableComboBox(placeholder="Tipo de compra")
        self._type.set_options(_PURCHASE_TYPES)
        self._priority = SearchableComboBox(placeholder="Prioridad")
        self._priority.set_options(_PRIORITIES)
        self._reason = StandardLineEdit(self)
        self._reason.setPlaceholderText("Justificación")
        self._lines = _LinesEditor(self)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Tipo", self._type)
        self.form.addRow("Prioridad", self._priority)
        self.form.addRow("Justificación", self._reason)
        self.form.addRow("Productos", self._lines)
        self.add_button_box(ok_text="Crear")

    def values(self) -> dict:
        return {"branch_id": self._branch.text().strip() or "MAIN",
                "purchase_type": self._type.current_id() or "INVENTORY",
                "priority": self._priority.current_id() or "NORMAL",
                "business_reason": self._reason.text().strip(),
                "lines": self._lines.lines()}


class OrderFormDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva orden de compra")
        self._supplier = StandardLineEdit(self)
        self._supplier.setPlaceholderText("Proveedor (ID)")
        self._branch = StandardLineEdit(self)
        self._branch.setPlaceholderText("Sucursal")
        self._warehouse = StandardLineEdit(self)
        self._warehouse.setPlaceholderText("Almacén")
        self._lines = _LinesEditor(self, with_price=True)
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Almacén", self._warehouse)
        self.form.addRow("Productos", self._lines)
        self.add_button_box(ok_text="Crear")

    def values(self) -> dict:
        return {"supplier_id": self._supplier.text().strip(),
                "branch_id": self._branch.text().strip() or "MAIN",
                "warehouse_id": self._warehouse.text().strip() or "MAIN",
                "lines": self._lines.lines()}


class InvoiceFormDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Capturar factura de proveedor")
        self._supplier = StandardLineEdit(self)
        self._supplier.setPlaceholderText("Proveedor (ID)")
        self._number = StandardLineEdit(self)
        self._number.setPlaceholderText("Número de factura")
        self._total = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._order = StandardLineEdit(self)
        self._order.setPlaceholderText("Orden de compra (ID, opcional)")
        self._uuid = StandardLineEdit(self)
        self._uuid.setPlaceholderText("UUID fiscal (opcional)")
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Número", self._number)
        self.form.addRow("Total", self._total)
        self.form.addRow("Orden de compra", self._order)
        self.form.addRow("UUID fiscal", self._uuid)
        self.add_button_box(ok_text="Capturar")

    def values(self) -> dict:
        total = self._total.decimal_value()
        return {"supplier_id": self._supplier.text().strip(),
                "invoice_number": self._number.text().strip(),
                "total": str(total if total is not None else "0"),
                "purchase_order_id": self._order.text().strip() or None,
                "uuid_fiscal": self._uuid.text().strip() or None}


class ReceiveOrderDialog(FormDialog):
    """Capture received/accepted quantities per order line."""

    def __init__(self, parent=None, *, order_detail: dict | None = None) -> None:
        super().__init__(parent, title="Registrar recepción")
        self._rows: list[tuple[str, DecimalInput, DecimalInput]] = []
        lines = (order_detail or {}).get("lines", [])
        if not lines:
            self.form.addRow(QLabel("La orden no tiene líneas.", self))
        for ln in lines:
            received = DecimalInput(self, precision=3, minimum="0")
            received.set_decimal(str(ln.get("ordered_quantity", "0")))
            accepted = DecimalInput(self, precision=3, minimum="0")
            accepted.set_decimal(str(ln.get("ordered_quantity", "0")))
            box = QHBoxLayout()
            box.addWidget(QLabel("Recibido", self))
            box.addWidget(received)
            box.addWidget(QLabel("Aceptado", self))
            box.addWidget(accepted)
            wrapper = QWidget(self)
            wrapper.setLayout(box)
            self.form.addRow(str(ln.get("product_id", ""))[:12], wrapper)
            self._rows.append((ln.get("product_id"), received, accepted))
        self.add_button_box(ok_text="Recibir")

    def receipt_lines(self) -> list[dict]:
        out = []
        for product_id, received, accepted in self._rows:
            rv = received.decimal_value()
            av = accepted.decimal_value()
            if rv is None or rv <= 0:
                continue
            out.append({"product_id": product_id, "received_quantity": str(rv),
                        "accepted_quantity": str(av if av is not None else rv)})
        return out


class ReasonDialog(FormDialog):
    def __init__(self, parent=None, *, title="Motivo", ok_text="Aceptar") -> None:
        super().__init__(parent, title=title)
        self._reason = StandardTextArea(self)
        self._reason.setPlaceholderText("Motivo (obligatorio)")
        self.form.addRow("Motivo", self._reason)
        self.add_button_box(ok_text=ok_text)

    def reason(self) -> str:
        return self._reason.toPlainText().strip()
