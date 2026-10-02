"""Focused 70/30 workspace for creating a direct purchase.

Sucursal y almacén DESTINO pertenecen al documento: se eligen aquí y se mandan
explícitos al guardar. La sesión sólo PRESELECCIONA; nunca es requisito para
abrir el formulario ni para guardar (el adaptador real de sesión no tiene almacén
activo, así que exigirlo hacía imposible guardar).

Cada acción deja una huella VISIBLE: un aviso destacado (Design System,
`role="banner"`), el folio en el resumen y la captura bloqueada tras guardar. Con
sólo una línea de texto pequeña el usuario reportaba "no pasa nada" aunque el
borrador sí se guardaba (medido 2026-09-25 sobre la base real).
"""

from decimal import Decimal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from backend.shared.ids import new_uuid
from frontend.desktop.components import (
    BarcodeInput, ColumnSpec, EntitySearchInput, PageHeader, SearchableComboBox,
    SectionCard, StandardTable, create_primary_button, create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
    AddCartLineDialog, EditLineCostDialog, confirm_purchase_flow,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
    FULFILLMENT_OPTIONS, KIND_OPTIONS, PAYMENT_CONDITION_OPTIONS, CartLineVM, error_text,
    money,
)
from frontend.desktop.modules.purchasing.widgets import PurchaseProcessStepper, PurchaseSummaryPanel
from frontend.desktop.themes.tokens import Spacing

_COLUMNS = [ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text"),
            ColumnSpec("Costo", "text"), ColumnSpec("Impuesto", "text"),
            ColumnSpec("Importe", "text")]
_MISSING_COST = "Falta costo"
_DESTINATION_REQUIRED = "Selecciona sucursal y almacén destino"
_NOT_SAVED = "Sin guardar"


class DirectPurchaseCreatePage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchaseCreatePage")
        self._presenter = presenter
        self._cart: list[CartLineVM] = []
        self._supplier_id = None
        self._source_requisition_id = None
        self._current_id = None
        self._folio = ""
        self._locked = False
        self._warehouse_ids: set[str] = set()
        # Un id de operación por INTENTO de captura: reintentar o hacer doble clic
        # reutiliza el mismo y el backend devuelve el documento ya creado en vez
        # de duplicarlo. Sólo cambia al empezar una compra nueva.
        self._operation_id = new_uuid()
        self._confirm_operation_id = new_uuid()
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.addWidget(PageHeader(title="Nueva compra directa",
                                  subtitle="Captura guiada con catálogo y revisión antes de confirmar.",
                                  icon=Icons.PURCHASES, compact=True))
        self.stepper = PurchaseProcessStepper(self)
        root.addWidget(self.stepper)
        self._notice = QLabel("", self)
        self._notice.setObjectName("directPurchaseNotice")
        self._notice.setProperty("role", "banner")
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
        self._load_destination()
        self._render()

    def _build_capture(self):
        card = SectionCard(title="Captura")
        body = QVBoxLayout()
        grid = QGridLayout()
        self._supplier = EntitySearchInput(
            self, provider=self._presenter.supplier_options,
            placeholder="Buscar proveedor por nombre o código",
            empty_reason_provider=self._presenter.supplier_search_reason)
        self._supplier.selected.connect(self._supplier_selected)
        self._barcode = BarcodeInput(self)
        self._barcode.scanned.connect(self._scan)
        self._branch = SearchableComboBox(placeholder="Sucursal destino")
        self._warehouse = SearchableComboBox(placeholder="Almacén destino")
        self._branch.selection_changed.connect(self._branch_changed)
        self._warehouse.selection_changed.connect(lambda *_: self._render())
        # Lo que se ve es lo que se guarda: sin opción elegida el guardado usaba
        # un valor por omisión que la pantalla no mostraba.
        # §11: QUÉ se compra y CÓMO llega son decisiones distintas. Antes un
        # solo combo mezclaba «con recepción inmediata» con «Servicio».
        self._kind = SearchableComboBox(placeholder="Tipo")
        self._kind.set_options(KIND_OPTIONS)
        self._kind.set_current_id(KIND_OPTIONS[0][0])
        self._kind.selection_changed.connect(lambda *_: self._fulfillment_changed())
        self._fulfillment = SearchableComboBox(placeholder="Surtido")
        self._fulfillment.set_options(FULFILLMENT_OPTIONS)
        self._fulfillment.set_current_id(FULFILLMENT_OPTIONS[0][0])
        self._fulfillment.selection_changed.connect(lambda *_: self._fulfillment_changed())
        self._origin_label = QLabel("Bodega de origen")
        self._origin = SearchableComboBox(placeholder="Bodega o punto de recolección")
        self._payment = SearchableComboBox(placeholder="Condición")
        self._payment.set_options(PAYMENT_CONDITION_OPTIONS)
        self._payment.set_current_id(PAYMENT_CONDITION_OPTIONS[0][0])
        self._payment.selection_changed.connect(lambda *_: self._render())
        # La fuente de pago ya NO se captura aquí: se pide en el diálogo de
        # confirmación, con el resumen de la compra a la vista.
        for col, (title, widget) in enumerate((("Proveedor", self._supplier),
                                               ("Escaneo", self._barcode))):
            grid.addWidget(QLabel(title), 0, col * 2)
            grid.addWidget(widget, 0, col * 2 + 1)
        grid.addWidget(QLabel("Sucursal destino"), 1, 0); grid.addWidget(self._branch, 1, 1)
        grid.addWidget(QLabel("Almacén destino"), 1, 2); grid.addWidget(self._warehouse, 1, 3)
        grid.addWidget(QLabel("Tipo"), 2, 0); grid.addWidget(self._kind, 2, 1)
        grid.addWidget(QLabel("Condición"), 2, 2); grid.addWidget(self._payment, 2, 3)
        grid.addWidget(QLabel("Surtido"), 3, 0); grid.addWidget(self._fulfillment, 3, 1)
        grid.addWidget(self._origin_label, 3, 2); grid.addWidget(self._origin, 3, 3)
        self._origin_label.setVisible(False)
        self._origin.setVisible(False)
        body.addLayout(grid)
        self._table = StandardTable(_COLUMNS, self)
        body.addWidget(self._table, stretch=1)
        actions = QHBoxLayout()
        self._add = create_secondary_button(self, "Agregar producto")
        self._add.clicked.connect(lambda *_: self._add_line())
        self._edit = create_secondary_button(self, "Editar costo")
        self._edit.clicked.connect(self._edit_cost)
        self._remove = create_secondary_button(self, "Quitar línea")
        self._remove.clicked.connect(self._remove_line)
        actions.addWidget(self._add); actions.addWidget(self._edit); actions.addWidget(self._remove)
        actions.addStretch(1)
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

    def refresh_permissions(self) -> None:
        """Re-evalúa la visibilidad de acciones sensibles tras login o cambio de permisos."""
        if hasattr(self, "_confirm"):
            self._confirm.setVisible(self._presenter.capabilities().direct_confirm)
        if not self._branch.has_selection():
            self._load_destination()
            self._render()

    def start_create(self):
        self._supplier.setFocus()

    # destino (sucursal + almacén) --------------------------------------------
    def _load_destination(self) -> None:
        """Carga las sucursales permitidas y PRESELECCIONA la de la sesión si es
        una de ellas. Sin sucursal preseleccionada el formulario abre igual: el
        usuario elige."""
        branches = self._presenter.branch_options()
        self._branch.set_options(branches)
        self._set_warehouses(None)
        branch_id, _warehouse = self._presenter.preselected_destination(branches)
        if branch_id:
            self._branch.set_current_id(branch_id)

    def _branch_changed(self, branch_id) -> None:
        self._set_warehouses(branch_id)
        self._render()

    def _set_warehouses(self, branch_id) -> None:
        """Recarga los almacenes de la sucursal y limpia cualquier selección
        anterior: un almacén de otra sucursal nunca sobrevive al cambio."""
        options = self._presenter.warehouse_options(branch_id) if branch_id else []
        self._warehouse.set_options(options)
        self._warehouse_ids = {wid for wid, _ in options}
        chosen = self._presenter.preselected_warehouse(options)
        if chosen:
            self._warehouse.set_current_id(chosen)

    def _destination_ids(self) -> tuple[str, str]:
        branch = self._branch.current_id() or ""
        warehouse = self._warehouse.current_id() or ""
        if warehouse and warehouse not in self._warehouse_ids:
            warehouse = ""
        return str(branch), str(warehouse)

    def _destination_text(self) -> str:
        if not (self._branch.has_selection() and self._warehouse.has_selection()):
            return "Selecciona sucursal y almacén"
        return f"{self._branch.currentText()} / {self._warehouse.currentText()}"

    # requisición -------------------------------------------------------------
    def start_from_requisition(self, detail):
        """``detail`` is a RequisitionDetailDTO (enterprise_presenter.py::requisition_detail),
        never a dict."""
        self._new_capture()
        self._source_requisition_id = str(detail.id)
        branch_id = str(getattr(detail, "branch_id", "") or "")
        if branch_id:
            self._branch.set_current_id(branch_id)
        lines = []
        for line in detail.lines:
            estimated = Decimal(str(line.estimated_unit_cost or "0"))
            lines.append(CartLineVM(
                str(line.product_id), self._presenter.product_label(str(line.product_id)),
                Decimal(str(line.quantity)),
                # Sin costo estimado NO se siembra un costo inventado: queda
                # marcado y el usuario debe capturarlo (el dominio exige > 0).
                estimated if estimated > 0 else Decimal("0")))
        self._cart = lines
        missing = any(line.cost_missing for line in self._cart)
        self._show(missing, "Origen: solicitud aprobada. Captura el costo de las líneas marcadas "
                            "«Falta costo»." if missing else
                   "Origen: solicitud aprobada. Confirma proveedor y condiciones.",
                   success=not missing)
        self._render()

    def _supplier_selected(self, supplier_id):
        self._supplier_id = str(supplier_id)
        self._fulfillment_changed()
        self._render()

    def _goods(self) -> bool:
        return (self._kind.current_id() or "GOODS") == "GOODS"

    def _mode(self) -> str:
        """Modo de la compra a partir de Tipo y Surtido."""
        if not self._goods():
            return self._kind.current_id()
        return ("DIRECT_WITH_IMMEDIATE_RECEIPT"
                if (self._fulfillment.current_id() or "IMMEDIATE_RECEIPT") == "IMMEDIATE_RECEIPT"
                else "DIRECT_WITH_PENDING_RECEIPT")

    def _fulfillment_changed(self) -> None:
        goods = self._goods()
        self._fulfillment.setEnabled(goods and not self._locked)
        pickup = goods and self._fulfillment.current_id() == "SUPPLIER_PICKUP"
        self._origin_label.setVisible(pickup)
        self._origin.setVisible(pickup)
        if pickup:
            options = self._presenter.supplier_origin_options(self._supplier_id)
            current = self._origin.current_id()
            self._origin.set_options(options)
            if current in dict(options):
                self._origin.set_current_id(current)
            elif len(options) == 1:
                self._origin.set_current_id(options[0][0])

    def _scan(self, code):
        if code:
            self._add_line(code)

    def _add_line(self, code=None):
        if self._locked:
            return
        branch_id, _warehouse = self._destination_ids()
        branch = branch_id or None
        presenter = self._presenter
        dialog = AddCartLineDialog(
            self,
            product_provider=lambda query: presenter.product_options(query, branch),
            empty_reason_provider=lambda query: presenter.product_search_reason(query, branch),
            profile_provider=presenter.purchase_profile,
            cost_variance=lambda pid, cost: presenter.price_variance(pid, cost, branch))
        if code:
            dialog.prefill_product(code)
        if dialog.exec_():
            line = dialog.line()
            if line:
                self._cart.append(line)
                self._show(False, "")
                self._render()
            else:
                self._show(True, "Selecciona un producto del catálogo y captura cantidad y costo mayores a cero.")

    def _edit_cost(self, *_):
        if self._locked:
            return
        row = self._table.currentRow()
        if not 0 <= row < len(self._cart):
            self._show(True, "Selecciona la línea cuyo costo quieres capturar.")
            return
        line = self._cart[row]
        dialog = EditLineCostDialog(self, description=line.description,
                                    current_cost=line.unit_cost)
        if dialog.exec_() and dialog.unit_cost() is not None:
            line.unit_cost = dialog.unit_cost()
            self._show(False, "")
            self._render()

    def _remove_line(self, *_):
        if self._locked:
            return
        row = self._table.currentRow()
        if 0 <= row < len(self._cart):
            self._cart.pop(row); self._render()

    # validación y guardado ---------------------------------------------------
    def _validate(self):
        errors = []
        if not self._supplier_id: errors.append("Selecciona un proveedor de la lista.")
        branch_id, warehouse_id = self._destination_ids()
        if not branch_id or not warehouse_id: errors.append(_DESTINATION_REQUIRED + ".")
        if not self._cart: errors.append("Agrega al menos un producto del catálogo.")
        if any(line.quantity <= 0 for line in self._cart):
            errors.append("Corrige las cantidades: deben ser mayores a cero.")
        missing = [line.description for line in self._cart if line.cost_missing]
        if missing:
            errors.append("Captura un costo unitario mayor a cero en: " + ", ".join(missing) + ".")
        if errors:
            self._show(True, "No se puede guardar todavía: " + " ".join(errors))
        return not errors

    def _save_draft(self, *_):
        if self._locked and self._current_id:
            self._show(False, f"La compra ya está guardada como {self._folio}. Pulsa «Confirmar "
                              "compra» para registrarla o «Nueva compra» para empezar otra.",
                       success=True)
            return True
        if not self._validate(): return False
        lines = list(self._cart)
        branch_id, warehouse_id = self._destination_ids()
        ok, message, data = self._presenter.create(
            supplier_id=self._supplier_id, lines=lines,
            mode=self._mode(),
            fulfillment_mode=(self._fulfillment.current_id() or "IMMEDIATE_RECEIPT")
            if self._goods() else None,
            origin_supplier_address_id=self._origin.current_id() or None
            if self._goods() and self._fulfillment.current_id() == "SUPPLIER_PICKUP" else None,
            payment_condition=self._payment.current_id() or PAYMENT_CONDITION_OPTIONS[0][0],
            branch_id=branch_id, warehouse_id=warehouse_id,
            source_requisition_id=self._source_requisition_id,
            operation_id=self._operation_id)
        if not ok:
            self._show(True, "No se guardó la compra: " + error_text(message, data))
            return False
        self._current_id = data.get("entity_id")
        self._folio = data.get("document_number") or ""
        if not data.get("already_registered"):
            self._presenter.record_price_variances(document_id=self._current_id, lines=lines,
                                                   branch_id=branch_id)
        self._set_locked(True)
        pending = data.get("status") == "PENDING_AUTHORIZATION"
        self._show(False, (f"Borrador {self._folio} guardado. " +
                           ("Supera tu límite de compra: debe autorizarse en Historial antes "
                            "de confirmarse." if pending else
                            "Revisa el resumen y pulsa «Confirmar compra» para registrarla.")),
                   success=True)
        self._render()
        self.stepper.set_current(3)
        return True

    def _continue_capture(self, *_):
        if self._locked:
            self._save_draft()
            return
        if self._validate():
            self.stepper.set_current(3)
            self._show(False, "Todo listo. Guarda el borrador o confirma la compra.", success=True)

    def _confirm_purchase(self, *_):
        if not self._save_draft(): return
        result = confirm_purchase_flow(self, self._presenter, self._current_id,
                                       operation_id=self._confirm_operation_id)
        if result is None:
            self._show(False, f"Confirmación cancelada; el borrador {self._folio} quedó guardado.",
                       success=True)
            return
        ok, message, data = result
        if not ok:
            self._show(True, f"No se confirmó {self._folio}: " + error_text(message, data))
            return
        folio = self._folio
        received = data.get("status") == "RECEIVED"
        destination = self._warehouse.currentText()
        self._new_capture()
        self._render()
        self._show(False, f"Compra {folio} confirmada." + (
            f" La mercancía entró al inventario de {destination}." if received else
            " Queda pendiente de recepción.") + " Ya puedes capturar la siguiente.",
            success=True)
        self.stepper.set_current(4)

    def _new_capture(self):
        """Estado limpio para la siguiente compra: ids de operación NUEVOS. El
        destino elegido se conserva (se compra varias veces al mismo lugar)."""
        self._cart = []; self._supplier_id = None; self._source_requisition_id = None
        self._current_id = None; self._folio = ""
        self._operation_id = new_uuid()
        self._confirm_operation_id = new_uuid()
        self._set_locked(False)
        if hasattr(self, "_supplier"): self._supplier.clear()

    def _clear(self, *_):
        folio = self._folio if self._current_id else ""
        self._new_capture()
        self._show(False, (f"Listo para una compra nueva. El borrador {folio} sigue en Historial."
                           if folio else "Captura cancelada; no se guardó nada."),
                   success=bool(folio))
        self._render()
        self.stepper.set_current(0)

    def _set_locked(self, locked: bool) -> None:
        """Tras guardar, la captura queda de sólo lectura: el borrador ya existe y
        editarla aquí no lo cambiaría. Se sigue desde «Confirmar compra» o se
        empieza otra con «Nueva compra»."""
        self._locked = locked
        for widget in (self._supplier, self._barcode, self._branch, self._warehouse,
                       self._kind, self._fulfillment, self._origin, self._payment,
                       self._add, self._edit, self._remove):
            widget.setEnabled(not locked)
        if not locked:
            self._fulfillment.setEnabled(self._goods())
        if hasattr(self, "_save"):
            self._save.setEnabled(not locked)
            self._cancel.setText("Nueva compra" if locked else "Cancelar captura")

    def _show(self, error, message, *, success=False):
        """Aviso destacado del Design System (`role="banner"`). El cambio de
        propiedad sólo repinta tras `unpolish/polish`."""
        self._notice.setProperty("state", "error" if error else ("success" if success else "ready"))
        self._notice.style().unpolish(self._notice)
        self._notice.style().polish(self._notice)
        self._notice.setText(message); self._notice.setVisible(bool(message))

    def _render(self):
        if not hasattr(self, "summary"): return
        if self.summary.actions.count() == 0: self._build_summary_actions()
        self._table.load_rows(
            [[line.description, _quantity_text(line),
              _MISSING_COST if line.cost_missing else
              money(line.unit_cost) + (" /kg" if line.priced_by_weight else ""),
              money(line.tax),
              "—" if line.cost_missing else money(line.line_total())] for line in self._cart],
            row_ids=[str(i) for i in range(len(self._cart))])
        totals = self._presenter.totals(self._cart)
        self.summary.update_summary(
            document=(f"{self._folio} · Borrador guardado" if self._current_id else _NOT_SAVED),
            supplier=self._supplier.selected_label(),
            destination=self._destination_text(),
            payment=self._payment.currentText(), **totals)
        if not self._locked:
            self.stepper.set_current(1 if self._supplier_id and not self._cart else
                                     2 if self._cart else 0)


def _quantity_text(line: CartLineVM) -> str:
    unit = line.purchase_unit or line.inventory_unit
    text = f"{line.quantity} {unit}".strip()
    if line.net_weight:
        text += f" · {line.net_weight} kg reales"
    return text
