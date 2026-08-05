"""Focused 70/30 workspace for creating a direct purchase."""

from decimal import Decimal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from frontend.desktop.components import (
    BarcodeInput, ColumnSpec, EntitySearchInput, PageHeader, SearchableComboBox,
    SectionCard, StandardTable, create_primary_button, create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import AddCartLineDialog
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
    MODE_OPTIONS, PAYMENT_CONDITION_OPTIONS, PAYMENT_SOURCE_OPTIONS, CartLineVM, money,
)
from frontend.desktop.modules.purchasing.widgets import PurchaseProcessStepper, PurchaseSummaryPanel
from frontend.desktop.themes.tokens import Spacing

_COLUMNS = [ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text"),
            ColumnSpec("Costo", "text"), ColumnSpec("Impuesto", "text"),
            ColumnSpec("Importe", "text")]


class DirectPurchaseCreatePage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseCreatePage")
        self._presenter = presenter
        self._cart: list[CartLineVM] = []
        self._supplier_id = None
        self._source_requisition_id = None
        self._current_id = None
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.addWidget(PageHeader(title="Nueva compra directa",
                                  subtitle="Captura guiada con catálogo y revisión antes de confirmar.",
                                  icon=Icons.PURCHASES, compact=True))
        self.stepper = PurchaseProcessStepper(self)
        root.addWidget(self.stepper)
        self._notice = QLabel("", self)
        self._notice.setWordWrap(True)
        self._notice.hide()
        root.addWidget(self._notice)
        split = QSplitter(Qt.Horizontal, self)
        split.addWidget(self._build_capture())
        self.summary = PurchaseSummaryPanel(self)
        split.addWidget(self.summary)
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        split.setSizes([700, 300])
        root.addWidget(split, stretch=1)
        self._render()

    def _build_capture(self):
        card = SectionCard(title="Captura")
        body = QVBoxLayout()
        grid = QGridLayout()
        self._supplier = EntitySearchInput(self, provider=self._presenter.supplier_options,
                                            placeholder="Buscar proveedor por nombre o código")
        self._supplier.selected.connect(self._supplier_selected)
        self._barcode = BarcodeInput(self)
        self._barcode.scanned.connect(self._scan)
        self._mode = SearchableComboBox(placeholder="Modo")
        self._mode.set_options(MODE_OPTIONS)
        self._payment = SearchableComboBox(placeholder="Condición")
        self._payment.set_options(PAYMENT_CONDITION_OPTIONS)
        self._source = SearchableComboBox(placeholder="Fuente de pago")
        self._source.set_options(PAYMENT_SOURCE_OPTIONS)
        for col, (title, widget) in enumerate((("Proveedor", self._supplier),
                                               ("Escaneo", self._barcode))):
            grid.addWidget(QLabel(title), 0, col * 2)
            grid.addWidget(widget, 0, col * 2 + 1)
        grid.addWidget(QLabel("Modalidad"), 1, 0); grid.addWidget(self._mode, 1, 1)
        grid.addWidget(QLabel("Condición"), 1, 2); grid.addWidget(self._payment, 1, 3)
        grid.addWidget(QLabel("Fuente"), 2, 0); grid.addWidget(self._source, 2, 1)
        body.addLayout(grid)
        self._table = StandardTable(_COLUMNS, self)
        body.addWidget(self._table, stretch=1)
        actions = QHBoxLayout()
        add = create_secondary_button(self, "Agregar producto")
        add.clicked.connect(self._add_line)
        remove = create_secondary_button(self, "Quitar línea")
        remove.clicked.connect(self._remove_line)
        actions.addWidget(add); actions.addWidget(remove); actions.addStretch(1)
        body.addLayout(actions)
        card.body().addLayout(body)
        return card

    def _build_summary_actions(self):
        self._save = create_secondary_button(self, "Guardar borrador")
        self._continue = create_primary_button(self, "Continuar")
        self._cancel = create_secondary_button(self, "Cancelar captura")
        self._confirm = create_success_button(self, "Confirmar compra")
        self._confirm.setVisible(self._presenter.capabilities().direct_confirm)
        for button, callback in ((self._save, self._save_draft),
                                 (self._continue, self._continue_capture),
                                 (self._cancel, self._clear),
                                 (self._confirm, self._confirm_purchase)):
            button.clicked.connect(callback)
            self.summary.actions.addWidget(button)

    def start_create(self):
        self._supplier.setFocus()

    def start_from_requisition(self, detail: dict):
        self._clear()
        self._source_requisition_id = str(detail["id"])
        self._cart = [CartLineVM(str(line["product_id"]),
                                 str(line.get("description") or line["product_id"]),
                                 Decimal(str(line["quantity"])),
                                 Decimal(str(line.get("estimated_unit_cost") or "0")),
                                 purchase_nature=str(line.get("purchase_nature") or "INVENTORY"))
                      for line in detail.get("lines", ())]
        self._show(False, "Origen: solicitud aprobada. Confirma proveedor y condiciones.")
        self._render()

    def _supplier_selected(self, supplier_id):
        self._supplier_id = str(supplier_id)
        self._render()

    def _scan(self, code):
        if code:
            self._add_line(code)

    def _add_line(self, code=None):
        dialog = AddCartLineDialog(self)
        if code:
            dialog.prefill_product(code)
        if dialog.exec_():
            line = dialog.line()
            if line:
                self._cart.append(line); self._render()
            else:
                self._show(True, "Selecciona un producto del catálogo y captura cantidad y costo válidos.")

    def _remove_line(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._cart):
            self._cart.pop(row); self._render()

    def _validate(self):
        errors = []
        if not self._supplier_id: errors.append("Selecciona un proveedor canónico.")
        if not self._cart: errors.append("Agrega al menos un producto del catálogo.")
        if any(line.quantity <= 0 or line.unit_cost < 0 for line in self._cart):
            errors.append("Corrige cantidades o costos inválidos.")
        self._show(bool(errors), " ".join(errors))
        return not errors

    def _save_draft(self):
        if not self._validate(): return False
        lines = list(self._cart)
        ok, message, data = self._presenter.create(
            supplier_id=self._supplier_id, lines=lines,
            mode=self._mode.current_id() or "DIRECT_WITH_IMMEDIATE_RECEIPT",
            payment_condition=self._payment.current_id() or "IMMEDIATE_PAYMENT",
            source_requisition_id=self._source_requisition_id)
        if ok:
            self._current_id = data.get("entity_id")
            self._presenter.record_price_variances(document_id=self._current_id, lines=lines)
            self.stepper.set_current(3)
        self._show(not ok, message)
        return ok

    def _continue_capture(self):
        if self._validate():
            self.stepper.set_current(3)
            self._show(False, "Revisa el resumen y guarda el borrador antes de confirmar.")

    def _confirm_purchase(self):
        if not self._current_id and not self._save_draft(): return
        ok, message, _ = self._presenter.confirm(self._current_id,
                                                  self._source.current_id() or None)
        self._show(not ok, message)
        if ok:
            self.stepper.set_current(4)

    def _clear(self):
        self._cart = []; self._supplier_id = None; self._source_requisition_id = None
        self._current_id = None
        if hasattr(self, "_supplier"): self._supplier.clear()
        self._show(False, "Captura cancelada; no se guardaron cambios locales.")
        self.stepper.set_current(0); self._render()

    def _show(self, error, message):
        self._notice.setProperty("state", "ERROR" if error else "READY")
        self._notice.setText(message); self._notice.setVisible(bool(message))

    def _render(self):
        if not hasattr(self, "summary"): return
        if self.summary.actions.count() == 0: self._build_summary_actions()
        self._table.load_rows([[line.description, str(line.quantity), money(line.unit_cost),
                                money(line.tax), money(line.line_total())] for line in self._cart],
                              row_ids=[str(i) for i in range(len(self._cart))])
        totals = self._presenter.totals(self._cart)
        self.summary.update_summary(supplier=self._supplier.selected_label(),
                                    destination=self._presenter.session_destination(),
                                    payment=self._payment.currentText(), **totals)
        self.stepper.set_current(1 if self._supplier_id and not self._cart else
                                 2 if self._cart else 0)
