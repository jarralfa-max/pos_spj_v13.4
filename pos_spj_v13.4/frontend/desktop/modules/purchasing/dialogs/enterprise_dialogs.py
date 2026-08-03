"""Dialogs for the enterprise procurement UI: requisition, order, invoice capture,
goods receipt, and a generic reason prompt. UI only — no business logic."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    DecimalInput,
    EntitySearchInput,
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
_PURCHASE_NATURES = [
    ("INVENTORY", "Inventario"), ("EXPENSE", "Gasto"), ("ASSET", "Activo"),
    ("SERVICE", "Servicio"), ("CONSUMABLE", "Consumible"),
    ("PACKAGING", "Empaque"), ("MAINTENANCE", "Mantenimiento"),
]


class _LinesEditor(QWidget):
    """A compact product-lines editor producing list[dict]. With or without price."""

    def __init__(self, parent=None, *, with_price: bool = False,
                 invoice: bool = False) -> None:
        super().__init__(parent)
        self._with_price = with_price
        self._invoice = invoice
        self._lines: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        self._product = StandardLineEdit(self)
        self._product.setPlaceholderText("Producto (código/ID)")
        self._qty = DecimalInput(self, precision=3, minimum="0")
        self._qty.setPlaceholderText("Cantidad")
        self._nature = SearchableComboBox(placeholder="Naturaleza")
        self._nature.set_options(_PURCHASE_NATURES)
        row.addWidget(self._product, stretch=2)
        row.addWidget(self._qty, stretch=1)
        row.addWidget(self._nature, stretch=1)
        if with_price:
            self._price = DecimalInput(self, precision=2, minimum="0")
            self._price.setPlaceholderText("Precio")
            row.addWidget(self._price, stretch=1)
        if invoice:
            self._tax = DecimalInput(self, precision=2, minimum="0")
            self._tax.setPlaceholderText("Impuestos")
            self._source_line = StandardLineEdit(self)
            self._source_line.setPlaceholderText("Línea de OC")
            row.addWidget(self._tax, stretch=1)
            row.addWidget(self._source_line, stretch=2)
        add = create_secondary_button(self, "Agregar")
        add.clicked.connect(self._add)
        row.addWidget(add)
        layout.addLayout(row)

        cols = [ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text"),
                ColumnSpec("Naturaleza", "text")]
        if with_price:
            cols.append(ColumnSpec("Precio", "text"))
        self._table = StandardTable(cols, self)
        layout.addWidget(self._table)

    def _add(self) -> None:
        product = self._product.text().strip()
        qty = self._qty.decimal_value()
        if not product or qty is None or qty <= 0:
            return
        line = {"product_id": product, "quantity": str(qty),
                "purchase_nature": self._nature.current_id() or "INVENTORY"}
        display = [product, str(qty), line["purchase_nature"]]
        if self._with_price:
            price = self._price.decimal_value()
            if price is None:
                return
            line["unit_price"] = str(price)
            line["estimated_unit_cost"] = str(price)
            display.append(str(price))
        if self._invoice:
            line["invoiced_quantity"] = line.pop("quantity")
            line["tax"] = str(self._tax.decimal_value() or "0")
            line["purchase_order_line_id"] = self._source_line.text().strip() or None
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
            row = [ln["product_id"], ln.get("quantity", ln.get("invoiced_quantity")),
                   ln["purchase_nature"]]
            if self._with_price:
                row.append(ln.get("unit_price", ""))
            rows.append(row)
        return rows

    def lines(self) -> list[dict]:
        return list(self._lines)

    def set_lines(self, lines: list[dict]) -> None:
        self._lines = [dict(line) for line in lines]
        self._table.load_rows(self._display_rows(),
                              row_ids=[str(i) for i in range(len(self._lines))])


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
        return {"branch_id": self._branch.text().strip(),
                "purchase_type": self._type.current_id() or "INVENTORY",
                "priority": self._priority.current_id() or "NORMAL",
                "business_reason": self._reason.text().strip(),
                "lines": self._lines.lines()}


class OrderFormDialog(FormDialog):
    def __init__(self, parent=None, *, source_requisition: dict | None = None,
                 branch_id: str = "", warehouse_id: str = "", supplier_provider=None) -> None:
        super().__init__(parent, title="Nueva orden de compra")
        self._supplier = EntitySearchInput(
            self, provider=supplier_provider,
            placeholder="Buscar proveedor por nombre o código")
        self._branch = StandardLineEdit(self)
        self._branch.setPlaceholderText("Sucursal")
        self._warehouse = StandardLineEdit(self)
        self._warehouse.setPlaceholderText("Almacén")
        self._lines = _LinesEditor(self, with_price=True)
        self._branch.setText(branch_id or str((source_requisition or {}).get("branch_id") or ""))
        self._warehouse.setText(warehouse_id)
        if source_requisition:
            self._lines.set_lines([{
                "product_id": line["product_id"], "quantity": line["quantity"],
                "purchase_nature": line.get("purchase_nature", "INVENTORY"),
                "unit_price": line.get("estimated_unit_cost") or "0",
            } for line in source_requisition.get("lines", ())])
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Almacén", self._warehouse)
        self.form.addRow("Productos", self._lines)
        self.add_button_box(ok_text="Crear")

    def values(self) -> dict:
        return {"supplier_id": self._supplier.selected_id() or "",
                "branch_id": self._branch.text().strip(),
                "warehouse_id": self._warehouse.text().strip(),
                "lines": self._lines.lines()}


class SupplierSelectionDialog(FormDialog):
    def __init__(self, parent=None, *, provider) -> None:
        super().__init__(parent, title="Crear RFQ desde solicitud")
        self._selected: list[tuple[str, str]] = []
        self._search = EntitySearchInput(
            self, provider=provider, placeholder="Buscar proveedor por nombre o código")
        self._search.selected.connect(self._add_supplier)
        self._table = StandardTable([ColumnSpec("Proveedor")], self)
        remove = create_secondary_button(self, "Quitar proveedor")
        remove.clicked.connect(self._remove_supplier)
        self.form.addRow("Proveedor", self._search)
        self.form.addRow("Invitados", self._table)
        self.form.addRow("", remove)
        self.add_button_box(ok_text="Crear RFQ")

    def _add_supplier(self, supplier_id) -> None:
        value = str(supplier_id or "")
        if value and value not in {item[0] for item in self._selected}:
            self._selected.append((value, self._search.selected_label() or "Proveedor"))
            self._render()

    def _remove_supplier(self) -> None:
        selected = self._table.selected_row_id()
        self._selected = [item for item in self._selected if item[0] != selected]
        self._render()

    def _render(self) -> None:
        self._table.load_rows([[label] for _, label in self._selected],
                              row_ids=[supplier_id for supplier_id, _ in self._selected])

    def supplier_ids(self) -> list[str]:
        return [supplier_id for supplier_id, _ in self._selected]


class InvoiceFormDialog(FormDialog):
    def __init__(self, parent=None, *, document_provider=None,
                 document_profile=None) -> None:
        super().__init__(parent, title="Capturar factura de proveedor")
        self._profile_provider = document_profile or (lambda _id: {})
        self._profile = {}
        self._document = EntitySearchInput(
            self, provider=document_provider,
            placeholder="Buscar orden o compra recibida")
        self._document.selected.connect(self._document_selected)
        self._supplier = QLabel("Selecciona un documento", self)
        self._number = StandardLineEdit(self)
        self._number.setPlaceholderText("Número de factura")
        self._total = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._uuid = StandardLineEdit(self)
        self._uuid.setPlaceholderText("UUID fiscal (opcional)")
        self._lines = _LinesEditor(self, with_price=True, invoice=True)
        self.form.addRow("Documento", self._document)
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Número", self._number)
        self.form.addRow("Total", self._total)
        self.form.addRow("UUID fiscal", self._uuid)
        self.form.addRow("Líneas", self._lines)
        self.add_button_box(ok_text="Capturar")

    def _document_selected(self, document_id) -> None:
        self._profile = self._profile_provider(str(document_id))
        self._supplier.setText(self._profile.get("supplier_name") or "—")
        source_key = ("purchase_order_line_id" if self._profile.get("document_type") == "PURCHASE_ORDER"
                      else "direct_purchase_line_id")
        self._lines.set_lines([{
            "product_id": line["product_id"],
            "invoiced_quantity": str(line["accepted_quantity"]),
            "purchase_nature": "INVENTORY", "unit_price": str(line["unit_price"]),
            "tax": str(line.get("tax") or "0"), source_key: line["source_line_id"],
        } for line in self._profile.get("lines", ())
            if Decimal(str(line["accepted_quantity"])) > 0])

    def values(self) -> dict:
        total = self._total.decimal_value()
        return {
            "supplier_id": self._profile.get("supplier_id") or "",
            "invoice_number": self._number.text().strip(),
            "total": str(total if total is not None else "0"),
            "purchase_order_id": self._document.selected_id()
            if self._profile.get("document_type") == "PURCHASE_ORDER" else None,
            "direct_purchase_id": self._document.selected_id()
            if self._profile.get("document_type") == "DIRECT_PURCHASE" else None,
            "uuid_fiscal": self._uuid.text().strip() or None,
            "lines": self._lines.lines(),
        }


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
