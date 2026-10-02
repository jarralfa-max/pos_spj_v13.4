"""Dialogs for the enterprise procurement UI: requisition, order, invoice capture,
goods receipt, and a generic reason prompt. UI only — no business logic."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtCore import QEvent, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from frontend.desktop.themes.tokens import DialogMetrics
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


_NATURE_LABELS = dict(_PURCHASE_NATURES)
_MISSING_PRICE = "Falta precio"


class _LinesEditor(QWidget):
    """Editor compacto de líneas de producto que produce ``list[dict]``.

    Con ``profile_provider`` la unidad de compra se ELIGE entre las que define
    Productos (nunca se teclea un factor: el caso de uso lo deriva del maestro).
    Con precio, una línea sin precio queda marcada «Falta precio» y se captura con
    «Capturar precio»; jamás se siembra un 0."""

    #: Cambió cualquier línea (agregar, quitar, editar).
    changed = pyqtSignal()

    def __init__(self, parent=None, *, with_price: bool = False,
                 invoice: bool = False, product_provider=None,
                 empty_reason_provider=None, profile_provider=None,
                 with_amounts: bool = False) -> None:
        super().__init__(parent)
        self._with_price = with_price
        self._with_amounts = with_amounts and with_price
        self._invoice = invoice
        self._profile_provider = profile_provider
        self._profile = None
        self._lines: list[dict] = []
        self._provider = product_provider or (lambda _q: [])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # El buscador ocupa su propio renglón: compartido con cantidad, unidad,
        # naturaleza y precio quedaba de unos cuantos caracteres.
        self._product = EntitySearchInput(
            self, provider=self._provider, placeholder="Buscar producto por nombre o código",
            empty_reason_provider=empty_reason_provider)
        layout.addWidget(self._product)
        row = QHBoxLayout()
        self._qty = DecimalInput(self, precision=3, minimum="0")
        self._qty.setPlaceholderText("Cantidad")
        self._unit = SearchableComboBox(placeholder="Unidad")
        self._unit.setVisible(profile_provider is not None)
        self._nature = SearchableComboBox(placeholder="Naturaleza")
        self._nature.set_options(_PURCHASE_NATURES)
        self._nature.set_current_id("INVENTORY")
        row.addWidget(self._qty, stretch=1)
        row.addWidget(self._unit, stretch=1)
        row.addWidget(self._nature, stretch=1)
        if with_price:
            self._price = DecimalInput(self, precision=2, minimum="0")
            self._price.setPlaceholderText("Precio")
            row.addWidget(self._price, stretch=1)
        if self._with_amounts:
            self._discount = DecimalInput(self, precision=2, minimum="0")
            self._discount.setPlaceholderText("Descuento")
            self._line_tax = DecimalInput(self, precision=2, minimum="0")
            self._line_tax.setPlaceholderText("IVA")
            row.addWidget(self._discount, stretch=1)
            row.addWidget(self._line_tax, stretch=1)
        if invoice:
            # Sin campo «Línea de OC»: pedía teclear un UUID. Las líneas de la
            # orden llegan precargadas y ligadas; una línea agregada a mano es
            # un cargo FUERA de la orden y así la conciliará.
            self._tax = DecimalInput(self, precision=2, minimum="0")
            self._tax.setPlaceholderText("Impuestos")
            row.addWidget(self._tax, stretch=1)
        add = create_secondary_button(self, "Agregar")
        add.clicked.connect(self._add)
        row.addWidget(add)
        layout.addLayout(row)

        cols = [ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text"),
                ColumnSpec("Naturaleza", "text")]
        if with_price:
            cols.append(ColumnSpec("Precio", "text"))
        if self._with_amounts:
            cols += [ColumnSpec("Descuento", "text"), ColumnSpec("IVA", "text"),
                     ColumnSpec("Subtotal", "text")]
        if invoice:
            cols += [ColumnSpec("Impuesto", "text"), ColumnSpec("Importe", "text")]
        self._table = StandardTable(cols, self)
        layout.addWidget(self._table)
        actions = QHBoxLayout()
        if invoice:
            # La factura rara vez coincide al centavo con lo precargado: se
            # corrige cantidad, precio o impuesto de la línea tal como viene.
            self._edit_button = create_secondary_button(self, "Editar línea")
            self._edit_button.clicked.connect(self._edit_invoice_line)
            actions.addWidget(self._edit_button)
        elif with_price:
            self._set_price_button = create_secondary_button(self, "Capturar precio")
            self._set_price_button.clicked.connect(self._capture_price)
            actions.addWidget(self._set_price_button)
        remove = create_secondary_button(self, "Quitar línea")
        remove.clicked.connect(self._remove)
        actions.addWidget(remove)
        actions.addStretch(1)
        layout.addLayout(actions)
        # "Agregar" callaba: si faltaba algo simplemente no hacía nada, y el
        # usuario no sabía por qué su producto no aparecía. Ahora lo dice.
        self._status = QLabel("", self)
        self._status.setObjectName("linesEditorStatus")
        self._status.setProperty("state", "error")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        layout.addWidget(self._status)
        # Enter en cantidad/precio AGREGA la línea. Sin esto la tecla llegaba al
        # diálogo y lo aceptaba a medio capturar.
        self._enter_adds = [self._qty]
        if with_price:
            self._enter_adds.append(self._price)
        if invoice:
            self._enter_adds.append(self._tax)
        for campo in self._enter_adds:
            campo.installEventFilter(self)
        self._product.selected.connect(self._product_selected)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - API de Qt
        if (obj in self._enter_adds and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)):
            self._add()
            return True
        return super().eventFilter(obj, event)

    # unidades (Productos) -------------------------------------------------------
    def _product_selected(self, product_id) -> None:
        if self._profile_provider is not None:
            self._profile = self._profile_provider(str(product_id)) if product_id else None
            units = list(self._profile.units) if self._profile is not None else []
            self._unit.set_options([(u.code, u.name if u.is_base else
                                     f"{u.name} ({_plain(u.factor_to_base)} "
                                     f"{self._profile.base_unit})") for u in units])
            if units:
                self._unit.set_current_id(next((u.code for u in units if u.is_base),
                                               units[0].code))
            self._unit.setEnabled(len(units) > 1)
            if self._with_price:
                self._price.setPlaceholderText(
                    "Precio por kg" if _weight_priced(self._profile) else "Precio")
        self._qty.setFocus()

    def _unit_text(self, line: dict) -> str:
        return line.get("unit_label") or line.get("purchase_unit") or ""

    # captura ---------------------------------------------------------------------
    def _problem(self, texto: str) -> None:
        self._status.setText(texto)
        self._status.setVisible(bool(texto))

    def pending_capture(self) -> bool:
        """¿Hay un producto elegido o una cantidad escrita sin agregar?"""
        return bool(self._product.selected_id()) or bool(self._qty.text().strip())

    def _add(self) -> None:
        product = self._product.selected_id()
        qty = self._qty.decimal_value()
        if not product:
            self._problem("Elige el producto de la lista de resultados (clic o Enter) "
                          "antes de agregarlo.")
            return
        if qty is None or qty <= 0:
            self._problem("Captura una cantidad mayor a cero.")
            return
        line = {"product_id": str(product), "product_label": self._product.selected_label(),
                "description": self._product.selected_label(),
                "quantity": str(qty),
                "purchase_nature": self._nature.current_id() or "INVENTORY"}
        if self._profile_provider is not None and self._profile is not None:
            unit = self._profile.unit(self._unit.current_id())
            if unit is None:
                self._problem("Elige la unidad de compra.")
                return
            line["purchase_unit"] = unit.code
            line["unit_label"] = unit.code
            if _weight_priced(self._profile):
                # Sólo para mostrar el estimado: el caso de uso decide la base
                # de precio con Productos.
                line["weight_factor"] = str(unit.factor_to_base)
        if self._with_price:
            price = self._price.decimal_value()
            # Decisión del usuario (2026-09-18): el costo debe ser mayor a cero;
            # el dominio también lo exige, esto sólo avisa antes.
            if price is None or price <= 0:
                self._problem("Captura un precio mayor a cero.")
                return
            line["unit_price"] = str(price)
            line["estimated_unit_cost"] = str(price)
        if self._with_amounts:
            discount = self._discount.decimal_value() or Decimal("0")
            if discount > qty * price:
                self._problem("El descuento no puede superar el importe de la línea.")
                return
            line["discount"] = str(discount)
            line["tax"] = str(self._line_tax.decimal_value() or Decimal("0"))
        if self._invoice:
            line["invoiced_quantity"] = line.pop("quantity")
            line["tax"] = str(self._tax.decimal_value() or "0")
        self._lines.append(line)
        self._refresh()
        self._problem("")
        self._product.clear()
        self._qty.clear()
        self._profile = None
        self._unit.set_options([])
        self._product._search.setFocus()
        if self._with_price:
            self._price.clear()
        if self._with_amounts:
            self._discount.clear()
            self._line_tax.clear()

    def _selected_index(self) -> int:
        row = self._table.currentRow()
        return row if 0 <= row < len(self._lines) else -1

    def _capture_price(self) -> None:
        index = self._selected_index()
        if index < 0:
            self._problem("Selecciona la línea cuyo precio quieres capturar.")
            return
        from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
            EditLineCostDialog,
        )
        line = self._lines[index]
        current = line.get("unit_price")
        dialog = EditLineCostDialog(self, description=line.get("product_label") or "",
                                    current_cost=Decimal(current) if current else None)
        if dialog.exec_() and dialog.unit_cost() is not None:
            line["unit_price"] = str(dialog.unit_cost())
            line["estimated_unit_cost"] = str(dialog.unit_cost())
            self._problem("")
            self._refresh()

    def _edit_invoice_line(self) -> None:
        index = self._selected_index()
        if index < 0:
            self._problem("Selecciona la línea que quieres corregir.")
            return
        line = self._lines[index]
        dialog = InvoiceLineDialog(self, line=line)
        if dialog.exec_():
            line.update(dialog.values())
            self._problem("")
            self._refresh()

    def _remove(self) -> None:
        index = self._selected_index()
        if index >= 0:
            self._lines.pop(index)
            self._refresh()

    def _refresh(self) -> None:
        self._table.load_rows(self._display_rows(),
                              row_ids=[str(i) for i in range(len(self._lines))])
        self.changed.emit()

    def invoice_total(self) -> Decimal:
        """Subtotal + impuesto de las líneas: la propuesta del total; el caso
        de uso lo vuelve a calcular y rechaza un total que no cuadre."""
        total = Decimal("0")
        for ln in self._lines:
            total += _invoice_amount(ln)
        return total

    def _display_rows(self) -> list[list[str]]:
        rows = []
        for ln in self._lines:
            quantity = ln.get("quantity", ln.get("invoiced_quantity"))
            unit = self._unit_text(ln)
            row = [ln.get("product_label") or "Producto",
                   f"{quantity} {unit}".strip(),
                   _NATURE_LABELS.get(ln["purchase_nature"], ln["purchase_nature"])]
            if self._with_price:
                row.append((ln["unit_price"] + (" /kg" if ln.get("weight_factor") else ""))
                           if ln.get("unit_price") else _MISSING_PRICE)
            if self._with_amounts:
                row += [ln.get("discount") or "0", ln.get("tax") or "0", _subtotal(ln)]
            if self._invoice:
                tax = Decimal(str(ln.get("tax") or "0"))
                row += [f"{tax:.2f}", f"{_invoice_amount(ln):.2f}"]
            rows.append(row)
        return rows

    def missing_price_labels(self) -> list[str]:
        if not self._with_price:
            return []
        return [ln.get("product_label") or "Producto" for ln in self._lines
                if not ln.get("unit_price") or Decimal(ln["unit_price"]) <= 0]

    def lines(self) -> list[dict]:
        """Backend-facing lines — never leak UI-only display fields."""
        return [{k: v for k, v in line.items()
                 if k not in ("product_label", "unit_label", "weight_factor")}
                for line in self._lines]

    def set_lines(self, lines: list[dict]) -> None:
        self._lines = [dict(line) for line in lines]
        self._refresh()


def _invoice_amount(line: dict) -> Decimal:
    quantity = Decimal(str(line.get("invoiced_quantity") or line.get("quantity") or "0"))
    return (quantity * Decimal(str(line.get("unit_price") or "0"))
            + Decimal(str(line.get("tax") or "0")))


class InvoiceLineDialog(FormDialog):
    """Corrige una línea de factura tal como la trae el papel del proveedor."""

    def __init__(self, parent=None, *, line: dict) -> None:
        super().__init__(parent, title="Editar línea de factura")
        self.form.addRow("Producto", QLabel(line.get("product_label") or "Producto", self))
        self._quantity = DecimalInput(self, precision=3, minimum="0")
        self._quantity.set_decimal(str(line.get("invoiced_quantity") or "0"))
        self._price = DecimalInput(self, precision=4, minimum="0")
        self._price.set_decimal(str(line.get("unit_price") or "0"))
        self._tax = DecimalInput(self, precision=2, minimum="0")
        self._tax.set_decimal(str(line.get("tax") or "0"))
        self.form.addRow("Cantidad facturada", self._quantity)
        self.form.addRow("Precio unitario", self._price)
        self.form.addRow("Impuesto de la línea", self._tax)
        self.add_button_box(ok_text="Aplicar")

    def values(self) -> dict:
        return {"invoiced_quantity": str(self._quantity.decimal_value() or "0"),
                "unit_price": str(self._price.decimal_value() or "0"),
                "tax": str(self._tax.decimal_value() or "0")}


def _weight_priced(profile) -> bool:
    """Peso variable con precio por kg (Productos lo decide, §49)."""
    if profile is None or not getattr(profile, "catch_weight", False):
        return False
    return (getattr(profile, "price_basis", None) or "PER_KILOGRAM") == "PER_KILOGRAM"


def _subtotal(line: dict) -> str:
    if not line.get("unit_price"):
        return "—"
    quantity = Decimal(str(line.get("quantity") or "0"))
    if line.get("weight_factor"):
        quantity *= Decimal(str(line["weight_factor"]))     # kg nominales (estimado)
    amount = quantity * Decimal(line["unit_price"]) - Decimal(str(line.get("discount") or "0"))
    return f"{amount:.2f}"


def _plain(value) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _lines_problem(editor) -> str | None:
    """Lo que impide aceptar un diálogo con líneas, o `None`."""
    if editor.pending_capture():
        return ("Tienes un producto capturado sin agregar: pulsa «Agregar» (o Enter en "
                "la cantidad) o bórralo.")
    if not editor.lines():
        return "Agrega al menos un producto."
    missing = editor.missing_price_labels()
    if missing:
        return ("Captura el precio de: " + ", ".join(missing)
                + ". Selecciona la línea y pulsa «Capturar precio».")
    return None


def _accept_or_warn(dialog, problema: str | None) -> bool:
    """Valida ANTES de cerrar. La página avisaba "Agrega al menos un producto"
    DESPUÉS de cerrarse el diálogo, con lo que se perdía todo lo capturado."""
    if problema:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.warning(dialog, dialog.windowTitle() or "Compras", problema)
        return False
    return True


class RequisitionFormDialog(FormDialog):
    def __init__(self, parent=None, *, product_provider=None,
                 empty_reason_provider=None, branch_options=None,
                 branch_id: str = "") -> None:
        """La sucursal se ELIGE, no se teclea.

        Era una caja de texto libre y arrancaba VACÍA: para crear una solicitud
        había que escribir a mano el UUID de la sucursal, así que en la práctica
        no se podía crear ninguna. `branch_options` llega ya acotado al alcance
        del usuario desde el presentador (§20, y el mismo orden que Transferencias).
        """
        super().__init__(parent, title="Nueva solicitud de compra", width=DialogMetrics.WIDTH_LG)
        self._branch = SearchableComboBox(placeholder="Sucursal")
        self._branch.set_options(list(branch_options or []))
        if branch_id:
            self._branch.set_current_id(branch_id)
        self._type = SearchableComboBox(placeholder="Tipo de compra")
        self._type.set_options(_PURCHASE_TYPES)
        self._priority = SearchableComboBox(placeholder="Prioridad")
        self._priority.set_options(_PRIORITIES)
        self._reason = StandardLineEdit(self)
        self._reason.setPlaceholderText("Justificación")
        self._lines = _LinesEditor(self, product_provider=product_provider,
                                   empty_reason_provider=empty_reason_provider)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Tipo", self._type)
        self.form.addRow("Prioridad", self._priority)
        self.form.addRow("Justificación", self._reason)
        self.form.addRow("Productos", self._lines)
        self.add_button_box(ok_text="Crear")

    def problem(self) -> str | None:
        if not self._branch.current_id():
            return "Elige la sucursal."
        return _lines_problem(self._lines)

    def accept(self) -> None:
        if _accept_or_warn(self, self.problem()):
            super().accept()

    def values(self) -> dict:
        return {"branch_id": str(self._branch.current_id() or ""),
                "purchase_type": self._type.current_id() or "INVENTORY",
                "priority": self._priority.current_id() or "NORMAL",
                "business_reason": self._reason.text().strip(),
                "lines": self._lines.lines()}


class OrderFormDialog(FormDialog):
    def __init__(self, parent=None, *, source_requisition=None,
                 branch_id: str = "", warehouse_id: str = "", supplier_provider=None,
                 product_provider=None, empty_reason_provider=None,
                 supplier_empty_reason=None, branch_options=None,
                 warehouse_options=None, warehouse_provider=None,
                 preselect_warehouse=None, profile_provider=None,
                 product_label_provider=None, on_submit=None,
                 origin_provider=None) -> None:
        """``source_requisition``, when given, is a RequisitionDetailDTO
        (frontend.../enterprise_presenter.py::requisition_detail) — never a dict.

        Sucursal y almacén se ELIGEN en el formulario (la sesión real nunca trae
        almacén: exigirlo impedía crear cualquier orden). Con ``on_submit`` el
        diálogo crea la orden él mismo y SÓLO se cierra si se creó: un rechazo
        del backend se muestra aquí sin perder lo capturado. ``operation_id`` es
        estable durante la captura (doble clic = una sola orden)."""
        super().__init__(parent, title="Nueva orden de compra", width=DialogMetrics.WIDTH_LG)
        from backend.shared.ids import new_uuid
        self.operation_id = new_uuid()
        self.result_data = None
        self._on_submit = on_submit
        self._origin_provider = origin_provider
        self._warehouse_provider = warehouse_provider
        self._preselect_warehouse = preselect_warehouse or (lambda _options: "")
        self._supplier = EntitySearchInput(
            self, provider=supplier_provider,
            placeholder="Buscar proveedor por nombre o código",
            empty_reason_provider=supplier_empty_reason)
        self._branch = SearchableComboBox(placeholder="Sucursal")
        self._branch.set_options(list(branch_options or []))
        self._warehouse = SearchableComboBox(placeholder="Almacén")
        self._warehouse.set_options(list(warehouse_options or []))
        self._lines = _LinesEditor(self, with_price=True, product_provider=product_provider,
                                   empty_reason_provider=empty_reason_provider,
                                   profile_provider=profile_provider, with_amounts=True)
        self._build_header()
        self._branch.selection_changed.connect(self._branch_changed)
        self._supplier.selected.connect(lambda *_: self._reload_origins())
        self._delivery_method.selection_changed.connect(lambda *_: self._pickup_changed())
        # La sucursal de la solicitud de origen manda sobre la de la sesión: la
        # orden tiene que surtir a quien lo pidió.
        preseleccion = (str(getattr(source_requisition, "branch_id", "") or "")
                        or branch_id)
        if preseleccion:
            self._branch.set_current_id(preseleccion)
        if warehouse_provider is None and warehouse_id:
            self._warehouse.set_current_id(warehouse_id)
        if source_requisition is not None:
            label_of = product_label_provider or (lambda _pid: "Producto")
            lines = []
            for line in source_requisition.lines:
                estimated = Decimal(str(line.estimated_unit_cost or "0"))
                label = label_of(str(line.product_id))
                item = {"product_id": line.product_id, "product_label": label,
                        "description": label, "quantity": line.quantity,
                        "purchase_nature": line.purchase_nature}
                # Sin costo estimado NO se siembra 0: la línea queda «Falta
                # precio» y el diálogo no acepta hasta capturarlo.
                if estimated > 0:
                    item["unit_price"] = str(estimated)
                    item["estimated_unit_cost"] = str(estimated)
                lines.append(item)
            self._lines.set_lines(lines)
        self._error = QLabel("", self)
        self._error.setProperty("role", "banner")
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Sucursal", self._branch)
        self.form.addRow("Almacén", self._warehouse)
        self.form.addRow("Fecha requerida", self._required_date)
        self.form.addRow("Condición de pago", self._payment_terms)
        self.form.addRow("Forma de entrega", self._delivery_method)
        self.form.addRow(self._origin_label, self._origin)
        self.form.addRow("Moneda", self._currency)
        self.form.addRow(self._exchange_label, self._exchange_rate)
        self.form.addRow("", self._more_toggle)
        self.form.addRow(self._more)
        self.form.addRow("Productos", self._lines)
        # Arriba, no al final: al final quedaba fuera de la vista en pantallas
        # bajas y el usuario sólo veía que "Crear orden" no hacía nada.
        self._root.insertWidget(0, self._error)
        self.add_button_box(ok_text="Crear orden")

    def _build_header(self) -> None:
        """Encabezado de la orden (§23). Lo habitual a la vista; centro de costo,
        proyecto, contrato, dirección y notas en «Más datos»."""
        from frontend.desktop.components import DateInput
        from frontend.desktop.modules.purchasing.enterprise_view_models import (
            CURRENCY_OPTIONS, DELIVERY_METHOD_OPTIONS, PAYMENT_TERMS_OPTIONS,
        )
        self._required_date = DateInput(self)
        self._payment_terms = SearchableComboBox(placeholder="Según el proveedor")
        self._payment_terms.set_options(PAYMENT_TERMS_OPTIONS)
        self._delivery_method = SearchableComboBox(placeholder="Forma de entrega")
        self._delivery_method.set_options(DELIVERY_METHOD_OPTIONS)
        self._delivery_method.set_current_id("SUPPLIER_DELIVERY")
        # §13: con recolección en proveedor se elige DE CUÁL de sus bodegas.
        self._origin_label = QLabel("Bodega / punto de recolección", self)
        self._origin = SearchableComboBox(placeholder="Bodega o punto de recolección")
        self._currency = SearchableComboBox(placeholder="Moneda")
        self._currency.set_options(CURRENCY_OPTIONS)
        self._currency.set_current_id("MXN")
        self._exchange_label = QLabel("Tipo de cambio", self)
        self._exchange_rate = DecimalInput(self, precision=4, minimum="0")
        self._currency.selection_changed.connect(lambda *_: self._currency_changed())
        self._more_toggle = create_secondary_button(self, "Más datos")
        self._more_toggle.setCheckable(True)
        self._more = QWidget(self)
        more = QFormLayout(self._more)
        more.setContentsMargins(0, 0, 0, 0)
        self._delivery_address = StandardLineEdit(self)
        self._delivery_address.setPlaceholderText("Dirección de entrega (si no es el almacén)")
        self._cost_center = StandardLineEdit(self)
        self._project = StandardLineEdit(self)
        self._contract = StandardLineEdit(self)
        self._notes = StandardTextArea(self)
        self._notes.setMaximumHeight(70)
        for title, widget in (("Dirección de entrega", self._delivery_address),
                              ("Centro de costo", self._cost_center),
                              ("Proyecto", self._project), ("Contrato", self._contract),
                              ("Notas", self._notes)):
            more.addRow(title, widget)
        self._more.setVisible(False)
        self._more_toggle.toggled.connect(self._more.setVisible)
        self._currency_changed()
        self._pickup_changed()

    def _pickup_changed(self) -> None:
        pickup = self._delivery_method.current_id() == "SUPPLIER_PICKUP"
        self._origin_label.setVisible(pickup)
        self._origin.setVisible(pickup)

    def _reload_origins(self) -> None:
        supplier_id = self._supplier.selected_id()
        options = (list(self._origin_provider(supplier_id))
                   if self._origin_provider is not None and supplier_id else [])
        self._origin.set_options(options)
        if len(options) == 1:
            self._origin.set_current_id(options[0][0])

    def _currency_changed(self) -> None:
        foreign = (self._currency.current_id() or "MXN") != "MXN"
        self._exchange_label.setVisible(foreign)
        self._exchange_rate.setVisible(foreign)

    def _branch_changed(self, branch_id) -> None:
        if self._warehouse_provider is None:
            return
        options = list(self._warehouse_provider(branch_id)) if branch_id else []
        self._warehouse.set_options(options)
        chosen = self._preselect_warehouse(options)
        if chosen:
            self._warehouse.set_current_id(chosen)

    def problem(self) -> str | None:
        if not self._supplier.selected_id():
            return "Elige el proveedor de la lista de resultados."
        if not self._branch.current_id():
            return "Elige la sucursal."
        if not self._warehouse.current_id():
            return "Elige el almacén que recibirá la mercancía."
        if self._delivery_method.current_id() == "SUPPLIER_PICKUP" and \
                not self._origin.current_id():
            if not self._origin.count() or self._origin.count() == 1 and \
                    self._origin.itemData(0) is None:
                return ("El proveedor no tiene bodegas ni puntos de recolección. Regístralos "
                        "en Proveedores → Domicilios (tipo Bodega o Punto de recolección).")
            return "Elige la bodega o punto de recolección."
        if (self._currency.current_id() or "MXN") != "MXN" and not (
                self._exchange_rate.decimal_value() or 0) > 0:
            return "Captura el tipo de cambio de la moneda elegida."
        return _lines_problem(self._lines)

    def error_text(self) -> str:
        return self._error.text()

    def _show_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.setVisible(bool(text))

    def accept(self) -> None:
        problema = self.problem()
        if problema:
            self._show_error(problema)
            return
        if self._on_submit is not None:
            ok, message, data = self._on_submit(self.values(), self.operation_id)
            if not ok:
                from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
                    error_text,
                )
                self._show_error("No se creó la orden: " + error_text(message, data))
                return
            self.result_data = (ok, message, data)
        self._show_error("")
        super().accept()

    def values(self) -> dict:
        currency = self._currency.current_id() or "MXN"
        return {"supplier_id": self._supplier.selected_id() or "",
                "branch_id": str(self._branch.current_id() or ""),
                "warehouse_id": str(self._warehouse.current_id() or ""),
                "lines": self._lines.lines(),
                "currency_code": currency,
                "exchange_rate": (str(self._exchange_rate.decimal_value())
                                  if currency != "MXN" else None),
                "payment_terms": self._payment_terms.current_id() or None,
                "required_date": self._required_date.date_value().isoformat(),
                "delivery_method": self._delivery_method.current_id() or None,
                "origin_supplier_address_id": (
                    self._origin.current_id() or None
                    if self._delivery_method.current_id() == "SUPPLIER_PICKUP" else None),
                "delivery_address": self._delivery_address.text().strip() or None,
                "cost_center": self._cost_center.text().strip() or None,
                "project_reference": self._project.text().strip() or None,
                "contract_reference": self._contract.text().strip() or None,
                "notes": self._notes.toPlainText().strip() or None}


class AcknowledgeOrderDialog(FormDialog):
    """Registrar la CONFIRMACIÓN del proveedor (§24). «Enviada» no es
    «aceptada»: aquí se captura su referencia, la fecha de entrega que promete
    y lo que confirma surtir por línea. Las diferencias se muestran como
    excepciones ANTES de guardar."""

    def __init__(self, parent=None, *, order_detail, on_submit=None) -> None:
        super().__init__(parent, title=f"Confirmación del proveedor — {order_detail.document_number}",
                         width=DialogMetrics.WIDTH_LG)
        from frontend.desktop.components import DateInput
        from backend.shared.ids import new_uuid
        self.operation_id = new_uuid()
        self.result_data = None
        self._on_submit = on_submit
        self._detail = order_detail
        self._error = QLabel("", self)
        self._error.setProperty("role", "banner")
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self._root.insertWidget(0, self._error)
        self._reference = StandardLineEdit(self)
        self._reference.setPlaceholderText("Folio o referencia del proveedor")
        self._delivery = DateInput(self)
        self._comments = StandardTextArea(self)
        self._comments.setMaximumHeight(70)
        self.form.addRow("Proveedor", QLabel(order_detail.supplier_name, self))
        self.form.addRow("Referencia", self._reference)
        self.form.addRow("Entrega confirmada", self._delivery)
        self._quantities: list[tuple[str, str, DecimalInput]] = []
        for line in order_detail.lines:
            quantity = DecimalInput(self, precision=3, minimum="0")
            quantity.set_decimal(str(line.ordered_quantity))
            quantity.value_changed.connect(self._refresh_exceptions)
            unit = f" {line.purchase_unit}" if line.purchase_unit else ""
            self.form.addRow(f"{line.product_name} (pedido {line.ordered_quantity}{unit})", quantity)
            self._quantities.append((line.id, str(line.ordered_quantity), quantity))
        self._delivery.dateChanged.connect(lambda *_: self._refresh_exceptions())
        self.form.addRow("Comentarios", self._comments)
        self._exceptions = QLabel("", self)
        self._exceptions.setWordWrap(True)
        self._exceptions.setProperty("role", "muted")
        self.form.addRow("Excepciones", self._exceptions)
        self.add_button_box(ok_text="Registrar confirmación")
        self._refresh_exceptions()

    def confirmed_quantities(self) -> dict[str, str]:
        return {line_id: str(widget.decimal_value() or Decimal("0"))
                for line_id, _ordered, widget in self._quantities}

    def exceptions_preview(self) -> list[str]:
        items = []
        for line, (line_id, ordered, widget) in zip(self._detail.lines, self._quantities):
            confirmed = widget.decimal_value() or Decimal("0")
            if confirmed != Decimal(ordered):
                items.append(f"{line.product_name}: confirma {confirmed.normalize():f} "
                             f"de {Decimal(ordered).normalize():f}")
        required = self._detail.required_date
        promised = self._delivery.date_value().isoformat()
        if required and promised > required:
            items.append(f"Entrega prometida {promised}, posterior a la requerida {required}")
        return items

    def _refresh_exceptions(self) -> None:
        items = self.exceptions_preview()
        self._exceptions.setText("\n".join(items) if items else "Sin excepciones")

    def error_text(self) -> str:
        return self._error.text()

    def values(self) -> dict:
        return {"supplier_reference": self._reference.text().strip(),
                "confirmed_delivery_date": self._delivery.date_value().isoformat(),
                "confirmed_quantities": self.confirmed_quantities(),
                "comments": self._comments.toPlainText().strip()}

    def accept(self) -> None:
        if not self._reference.text().strip():
            self._error.setText("Captura la referencia o folio del proveedor.")
            self._error.show()
            return
        if self._on_submit is not None:
            ok, message, data = self._on_submit(self.values(), self.operation_id)
            if not ok:
                from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
                    error_text,
                )
                self._error.setText(error_text(message, data))
                self._error.show()
                return
            self.result_data = (ok, message, data)
        super().accept()


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


class QuoteCaptureDialog(FormDialog):
    """Capture what one invited supplier quoted back — restricted to the
    suppliers actually invited to this RFQ, never a free-text/global search."""

    def __init__(self, parent=None, *, invited_suppliers: list[tuple[str, str]],
                 product_provider=None, empty_reason_provider=None) -> None:
        super().__init__(parent, title="Capturar cotización de proveedor", width=DialogMetrics.WIDTH_LG)
        self._supplier = SearchableComboBox(placeholder="Proveedor invitado")
        self._supplier.set_options(invited_suppliers)
        self._lead_time = DecimalInput(self, precision=0, minimum="0")
        self._lines = _LinesEditor(self, with_price=True, product_provider=product_provider,
                                   empty_reason_provider=empty_reason_provider)
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Plazo de entrega (días)", self._lead_time)
        self.form.addRow("Líneas cotizadas", self._lines)
        self.add_button_box(ok_text="Capturar")

    def values(self) -> dict:
        return {"supplier_id": self._supplier.current_id() or "",
                "lead_time_days": int(self._lead_time.decimal_value() or 0),
                "lines": self._lines.lines()}


class AwardDialog(FormDialog):
    """Comparación de cotizaciones por producto: cada fila es una (producto,
    proveedor) cotizada; ★ marca la de menor precio. Un clic por producto
    elige la línea ganadora — pueden quedar proveedores distintos por
    producto (adjudicación dividida), tal como lo soporta el dominio."""

    def __init__(self, parent=None, *, comparison_rows) -> None:
        super().__init__(parent, title="Comparar y adjudicar cotizaciones")
        self._rows = list(comparison_rows)
        self._selected: dict[str, str] = {}
        self._table = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Proveedor"),
            ColumnSpec("Precio unitario", "numeric"), ColumnSpec("Plazo (días)", "numeric"),
            ColumnSpec("Mejor precio"),
        ], self)
        self._table.load_rows([
            [r.product_name, r.supplier_name, f"{r.unit_price} {r.currency_code}",
             str(r.lead_time_days), "★" if r.is_best else ""] for r in self._rows],
            row_ids=[r.quote_line_id for r in self._rows])
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        self.form.addRow("Cotizaciones por producto", self._table)
        self._picked_label = QLabel(
            "Selecciona una línea por producto (clic en la fila).", self)
        self._picked_label.setWordWrap(True)
        self.form.addRow("", self._picked_label)
        self._reason = StandardTextArea(self)
        self._reason.setPlaceholderText("Justificación de la adjudicación (obligatoria)")
        self.form.addRow("Justificación", self._reason)
        self.add_button_box(ok_text="Adjudicar")

    def _on_row_selected(self) -> None:
        line_id = self._table.selected_row_id()
        row = next((r for r in self._rows if r.quote_line_id == line_id), None)
        if row is None:
            return
        self._selected[row.product_id] = line_id
        chosen = "; ".join(
            f"{pid} → {next(r.supplier_name for r in self._rows if r.quote_line_id == lid)}"
            for pid, lid in self._selected.items())
        self._picked_label.setText(f"Seleccionado: {chosen}")

    def award_lines(self) -> list[dict]:
        reason = self._reason.toPlainText().strip()
        lines = []
        for line_id in self._selected.values():
            row = next(r for r in self._rows if r.quote_line_id == line_id)
            lines.append({"quote_line_id": row.quote_line_id, "supplier_id": row.supplier_id,
                          "awarded_quantity": row.quantity, "justification": reason})
        return lines

    def reason(self) -> str:
        return self._reason.toPlainText().strip()


class GenerateOrdersDialog(FormDialog):
    """Adjudicación → una orden por proveedor. Muestra qué se va a generar (y qué
    ya existe), pide el almacén que recibirá y genera desde el propio diálogo:
    sólo se cierra si todo se generó; si algo falla lo dice aquí y reintentar
    completa sólo lo que falta (idempotente por proveedor)."""

    def __init__(self, parent=None, *, award: dict, warehouse_options=None,
                 preselected_warehouse: str = "", on_submit=None) -> None:
        super().__init__(parent, title="Generar órdenes de compra",
                         width=DialogMetrics.WIDTH_LG)
        from backend.shared.ids import new_uuid
        self.operation_id = new_uuid()
        self.result_data = None
        self._award = award
        self._on_submit = on_submit
        self._error = QLabel("", self)
        self._error.setProperty("role", "banner")
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self._root.insertWidget(0, self._error)
        self._table = StandardTable([ColumnSpec("Proveedor"), ColumnSpec("Líneas", "numeric"),
                                     ColumnSpec("Total", "numeric"), ColumnSpec("Orden")], self)
        from PyQt5.QtWidgets import QHeaderView
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        suppliers = list(award.get("suppliers") or [])
        self._table.load_rows([
            [s["supplier_name"], str(s["lines"]), f"${Decimal(s['total']):,.2f}",
             s["order_number"] or "Por generar"] for s in suppliers],
            row_ids=[s["supplier_id"] for s in suppliers])
        self._warehouse = SearchableComboBox(placeholder="Almacén que recibe")
        self._warehouse.set_options(list(warehouse_options or []))
        if preselected_warehouse:
            self._warehouse.set_current_id(preselected_warehouse)
        pending = [s for s in suppliers if not s["order_number"]]
        self.form.addRow("Proveedores adjudicados", self._table)
        self.form.addRow("Almacén", self._warehouse)
        box = self.add_button_box(ok_text=f"Generar {len(pending)} orden(es)")
        self._ok = box.button(QDialogButtonBox.Ok)
        if not pending:
            self._ok.setEnabled(False)
            self._show_error("Todas las órdenes de esta adjudicación ya están generadas.")

    def error_text(self) -> str:
        return self._error.text()

    def _show_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.setVisible(bool(text))

    def warehouse_id(self) -> str:
        return str(self._warehouse.current_id() or "")

    def accept(self) -> None:
        if not self.warehouse_id():
            self._show_error("Elige el almacén que recibirá la mercancía.")
            return
        if self._on_submit is not None:
            ok, message, data = self._on_submit(self.warehouse_id(), self.operation_id)
            if not ok:
                from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
                    error_text,
                )
                self._show_error(error_text(message, data))
                return
            self.result_data = (ok, message, data)
        self._show_error("")
        super().accept()


class InvoiceFormDialog(FormDialog):
    def __init__(self, parent=None, *, document_provider=None,
                 document_profile=None, product_provider=None,
                 empty_reason_provider=None) -> None:
        super().__init__(parent, title="Capturar factura de proveedor", width=DialogMetrics.WIDTH_LG)
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
        self._lines = _LinesEditor(self, with_price=True, invoice=True,
                                   product_provider=product_provider,
                                   empty_reason_provider=empty_reason_provider)
        self.form.addRow("Documento", self._document)
        self.form.addRow("Proveedor", self._supplier)
        self.form.addRow("Número", self._number)
        self.form.addRow("Total", self._total)
        self.form.addRow("UUID fiscal", self._uuid)
        self.form.addRow("Líneas", self._lines)
        self._total_hint = QLabel(
            "El total se propone con las líneas; corrígelo al de la factura. Si no "
            "cuadra con las líneas, la factura no se captura.", self)
        self._total_hint.setWordWrap(True)
        self._total_hint.setProperty("role", "muted")
        self.form.addRow("", self._total_hint)
        self._lines.changed.connect(self._propose_total)
        self.add_button_box(ok_text="Capturar")

    def _propose_total(self) -> None:
        self._total.set_decimal(str(self._lines.invoice_total().quantize(Decimal("0.01"))))

    def _document_selected(self, document_id) -> None:
        self._profile = self._profile_provider(str(document_id))
        self._supplier.setText(self._profile.get("supplier_name") or "—")
        source_key = ("purchase_order_line_id" if self._profile.get("document_type") == "PURCHASE_ORDER"
                      else "direct_purchase_line_id")
        # Lo PENDIENTE de facturar (aceptado − ya facturado): prellenar todo lo
        # aceptado hacía que la segunda factura parcial saliera «diferencia de
        # cantidad». Precio neto de descuento e impuesto proporcional, igual
        # que los esperará la conciliación.
        def pending(line) -> Decimal:
            return Decimal(str(line.get("pending_quantity", line["accepted_quantity"])))

        self._lines.set_lines([{
            "product_id": line["product_id"],
            "product_label": line.get("product_label") or "Producto",
            "unit_label": line.get("purchase_unit") or "",
            "invoiced_quantity": str(pending(line)),
            "purchase_nature": "INVENTORY", "unit_price": str(line["unit_price"]),
            "tax": str(line.get("tax") or "0"), source_key: line["source_line_id"],
        } for line in self._profile.get("lines", ()) if pending(line) > 0])

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


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0"))
    except ArithmeticError:
        return Decimal("0")


def _receipt_requirements(profile, purchase_unit: str = "") -> dict:
    """Lo que el producto exige al recibir — por CAPACIDADES de Productos
    (§49), nunca por categoría — y cómo se recibe su presentación (§27)."""
    unit = profile.unit(purchase_unit) if profile is not None and hasattr(
        profile, "unit") else None
    return {
        "unit_factor": getattr(unit, "factor_to_base", None) if unit is not None
        and not unit.is_base else None,
        "base_unit": getattr(profile, "base_unit", "") or "",
        "fractional": True if unit is None or unit.is_base
        else bool(getattr(unit, "fractional_receipt", True)),
        "lot_required": bool(getattr(profile, "lot_controlled", False)),
        "expiration_required": bool(getattr(profile, "expiration_controlled", False)),
        "weight_required": bool(getattr(profile, "catch_weight", False)),
        "temperature_required": bool(getattr(profile, "temperature_tracked", False)),
    }


def _missing_trace(capture: dict) -> list[str]:
    missing = []
    if capture.get("lot_required") and not capture.get("lot"):
        missing.append("lote")
    if capture.get("expiration_required") and not capture.get("expiration"):
        missing.append("caducidad")
    if capture.get("weight_required") and not _decimal(capture.get("net_weight")) > 0:
        missing.append("peso real")
    if capture.get("temperature_required") and capture.get("temperature") in (None, ""):
        missing.append("temperatura")
    return missing


class ReceiveOrderLineDialog(FormDialog):
    """Recepción de UNA línea: cantidades, motivo del rechazo y sólo la
    trazabilidad que el producto exige."""

    def __init__(self, parent=None, *, capture: dict) -> None:
        from frontend.desktop.modules.purchasing.dialogs.origin_dialogs import _TraceFields
        super().__init__(parent, title=f"Recibir — {capture['product_label']}",
                         width=DialogMetrics.WIDTH_LG)
        self._capture = capture
        self._trace = _TraceFields()
        self.form.addRow("Pendiente", QLabel(
            f"{_plain(capture['pending'])} {capture['unit']}".strip(), self))
        # §27: una presentación que no se recibe en fracción sólo admite
        # unidades completas; si la admite, «4 costales + 22 kg sueltos».
        precision = 3 if capture.get("fractional", True) else 0
        self._received = DecimalInput(self, precision=precision, minimum="0")
        self._received.set_decimal(str(capture.get("received") or "0"))
        self._accepted = DecimalInput(self, precision=precision, minimum="0")
        self._accepted.set_decimal(str(capture.get("accepted") or "0"))
        self._loose = None
        if capture.get("fractional", True) and capture.get("unit_factor"):
            self._loose = DecimalInput(self, precision=3, minimum="0", nullable=True)
            self._loose.setPlaceholderText(
                f"Sueltos en {capture.get('base_unit') or 'unidad base'}")
        self._reason = StandardLineEdit(self)
        self._reason.setPlaceholderText("Motivo del rechazo (si se acepta menos)")
        self._reason.setText(capture.get("rejection_reason") or "")
        self.form.addRow("Recibido", self._received)
        if self._loose is not None:
            self.form.addRow(f"Más sueltos ({capture.get('base_unit')})", self._loose)
        self.form.addRow("Aceptado", self._accepted)
        self.form.addRow("Rechazo", self._reason)
        self._trace._build_trace(self, weight_label="Peso real (kg)")
        self._trace._apply_requirements(capture)
        if capture.get("lot"):
            self._trace._lot.setText(capture["lot"])
        if capture.get("net_weight"):
            self._trace._weight.set_decimal(str(capture["net_weight"]))
        if capture.get("temperature") not in (None, ""):
            self._trace._temperature.set_decimal(str(capture["temperature"]))
        self._error = QLabel("", self)
        self._error.setProperty("role", "banner")
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        self.form.addRow("", self._error)
        self.add_button_box(ok_text="Aplicar")

    def problem(self) -> str | None:
        received = (self._received.decimal_value() or Decimal("0")) + self._loose_units()
        accepted = (self._accepted.decimal_value() or Decimal("0")) + self._loose_units()
        if accepted > received:
            return "Lo aceptado no puede exceder lo recibido."
        if received > 0:
            return self._trace._trace_problem(self._capture, self._capture["product_label"],
                                              applies=accepted > 0)
        return None

    def accept(self) -> None:
        problem = self.problem()
        if problem:
            self._error.setText(problem)
            self._error.setVisible(True)
            return
        super().accept()

    def _loose_units(self) -> Decimal:
        """Los sueltos (22 kg) en la unidad de compra (22 / 25 = 0.88 costal)."""
        if self._loose is None:
            return Decimal("0")
        loose = self._loose.decimal_value() or Decimal("0")
        factor = Decimal(str(self._capture.get("unit_factor") or "1"))
        return loose / factor if factor > 0 else Decimal("0")

    def values(self) -> dict:
        trace = self._trace._trace_values()
        weight = self._trace._weight.decimal_value()
        loose = self._loose_units()
        received = (self._received.decimal_value() or Decimal("0")) + loose
        accepted = (self._accepted.decimal_value() or Decimal("0")) + loose
        return {"received": _plain(received) if received else "0",
                "accepted": _plain(accepted) if accepted else "0",
                "rejection_reason": self._reason.text().strip(),
                "lot": trace["lot_number"] or "",
                "expiration": trace["expiration_date"],
                "temperature": trace["temperature"],
                "net_weight": str(weight) if weight else ""}


class ReceiveOrderDialog(FormDialog):
    """Recepción de la orden por LÍNEA (ligada a su línea de OC).

    Antes recibía por producto, en una sola fila sin lote, caducidad, peso ni
    temperatura: un producto que los exige (FASE 11) no se podía recibir desde
    aquí. Las líneas sin requisitos llegan prellenadas con lo pendiente (una
    orden sencilla se recibe con un clic); las demás piden «Capturar línea».
    """

    def __init__(self, parent=None, *, order_detail=None, profile_provider=None) -> None:
        super().__init__(parent, title="Registrar recepción", width=DialogMetrics.WIDTH_LG)
        self._captures: list[dict] = []
        for ln in (order_detail.lines if order_detail is not None else []):
            pending = _decimal(ln.ordered_quantity) - _decimal(ln.received_quantity)
            if pending <= 0:
                continue
            profile = profile_provider(ln.product_id) if profile_provider else None
            capture = {"line_id": ln.id, "product_id": ln.product_id,
                       "product_label": getattr(ln, "product_name", "") or "Producto",
                       "unit": ln.purchase_unit or "", "pending": pending,
                       **_receipt_requirements(profile, ln.purchase_unit or "")}
            simple = not any(capture[k] for k in ("lot_required", "expiration_required",
                                                  "weight_required", "temperature_required"))
            capture["received"] = capture["accepted"] = pending if simple else Decimal("0")
            self._captures.append(capture)
        if not self._captures:
            self.form.addRow(QLabel("La orden no tiene cantidades pendientes de recibir.", self))
        self._table = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Pendiente"), ColumnSpec("Recibido"),
            ColumnSpec("Aceptado"), ColumnSpec("Trazabilidad")], self)
        self.form.addRow(self._table)
        actions = QHBoxLayout()
        capture_button = create_secondary_button(self, "Capturar línea")
        capture_button.clicked.connect(self._capture_selected)
        skip_button = create_secondary_button(self, "No recibir esta línea")
        skip_button.clicked.connect(self._skip_selected)
        actions.addWidget(capture_button)
        actions.addWidget(skip_button)
        actions.addStretch(1)
        self.form.addRow(actions)
        self._error = QLabel("", self)
        self._error.setProperty("role", "banner")
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        self.form.addRow(self._error)
        self._refresh()
        self.add_button_box(ok_text="Recibir")

    def _trace_text(self, capture: dict) -> str:
        if _decimal(capture.get("received")) <= 0:
            return "Sin recibir"
        missing = _missing_trace(capture)
        if missing and _decimal(capture.get("accepted")) > 0:
            return "Falta: " + ", ".join(missing)
        parts = [f"Lote {capture['lot']}" if capture.get("lot") else "",
                 f"{capture['net_weight']} kg" if capture.get("net_weight") else "",
                 f"Cad. {capture['expiration']}" if capture.get("expiration") else "",
                 f"{capture['temperature']} °C" if capture.get("temperature") else ""]
        return " · ".join(p for p in parts if p) or "Completa"

    def _refresh(self) -> None:
        self._table.load_rows([[
            c["product_label"], f"{_plain(c['pending'])} {c['unit']}".strip(),
            _plain(c["received"]), _plain(c["accepted"]), self._trace_text(c),
        ] for c in self._captures], row_ids=[c["line_id"] for c in self._captures])

    def _selected_capture(self) -> dict | None:
        row = self._table.currentRow()
        return self._captures[row] if 0 <= row < len(self._captures) else None

    def _capture_selected(self) -> None:
        capture = self._selected_capture()
        if capture is None:
            self._show("Selecciona la línea que vas a recibir.")
            return
        dialog = ReceiveOrderLineDialog(self, capture=capture)
        if dialog.exec_():
            capture.update(dialog.values())
            self._show("")
            self._refresh()

    def _skip_selected(self) -> None:
        capture = self._selected_capture()
        if capture is not None:
            capture["received"] = capture["accepted"] = Decimal("0")
            self._refresh()

    def _show(self, text: str) -> None:
        self._error.setText(text)
        self._error.setVisible(bool(text))

    def problem(self) -> str | None:
        if not any(_decimal(c.get("received")) > 0 for c in self._captures):
            return "Captura al menos una línea recibida."
        for c in self._captures:
            if _decimal(c.get("received")) > 0 and _decimal(c.get("accepted")) > 0:
                missing = _missing_trace(c)
                if missing:
                    return (f"{c['product_label']}: falta {', '.join(missing)}. Selecciona "
                            "la línea y pulsa «Capturar línea».")
        return None

    def accept(self) -> None:
        problem = self.problem()
        if problem:
            self._show(problem)
            return
        super().accept()

    def receipt_lines(self) -> list[dict]:
        out = []
        for c in self._captures:
            received = _decimal(c.get("received"))
            if received <= 0:
                continue
            line = {"product_id": c["product_id"], "purchase_order_line_id": c["line_id"],
                    "received_quantity": str(received),
                    "accepted_quantity": str(_decimal(c.get("accepted")))}
            for key in ("lot", "expiration", "net_weight", "temperature"):
                if c.get(key) not in (None, ""):
                    line[key] = str(c[key])
            if c.get("rejection_reason"):
                line["rejection_reason"] = c["rejection_reason"]
            out.append(line)
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
