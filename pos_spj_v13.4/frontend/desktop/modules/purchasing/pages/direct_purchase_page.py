"""Direct-purchase capture page (PUR-5) — proveedor, escaneo, carrito, peso/pollo,
totales, financiero, autorización en caliente, recepción y reverso.

UI only: every read/mutation is delegated to the presenter; totals come from the
presenter (Decimal). No SQL, no business rules, no money math in the widget.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    BarcodeInput,
    ColumnSpec,
    EntitySearchInput,
    PageHeader,
    SearchInput,
    SearchableComboBox,
    SectionCard,
    StandardTable,
    ViewState,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
    create_success_button,
    create_warning_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.direct_purchase_dialogs import (
    AddCartLineDialog,
    HotAuthorizationDialog,
    ReverseReasonDialog,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
    MODE_OPTIONS,
    PAYMENT_CONDITION_OPTIONS,
    PAYMENT_SOURCE_OPTIONS,
    CartLineVM,
    money,
    status_es,
)
from frontend.desktop.themes.tokens import Spacing

_CART_COLUMNS = [
    ColumnSpec("Producto", "text"), ColumnSpec("Cantidad", "text"),
    ColumnSpec("Costo", "text"), ColumnSpec("IVA", "text"), ColumnSpec("Importe", "text"),
]
_LIST_COLUMNS = [
    ColumnSpec("Folio", "text"), ColumnSpec("Proveedor", "text"),
    ColumnSpec("Estado", "status"), ColumnSpec("Pago", "text"),
    ColumnSpec("Total", "text"), ColumnSpec("Fecha", "text"),
]


class DirectPurchasePage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("directPurchasePage")
        self._presenter = presenter
        self._cart: list[CartLineVM] = []
        self._supplier_id: str | None = None
        self._current_id: str | None = None
        self._current_status: str | None = None
        self._loaded = False

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Compra directa",
            subtitle="Abastecimiento rápido con proveedor, escaneo, recepción y reverso.",
            icon=Icons.PURCHASES if hasattr(Icons, "PURCHASES") else Icons.FINANCE,
            compact=True)
        root.addWidget(self.header)

        root.addWidget(self._build_capture_card())
        root.addWidget(self._build_recent_card(), stretch=1)

        self._refresh_action_state()

    # capture -----------------------------------------------------------------
    def _build_capture_card(self) -> QWidget:
        card = SectionCard(title="Nueva compra")
        body = QVBoxLayout()
        body.setSpacing(Spacing.SM)

        grid = QGridLayout()
        grid.setHorizontalSpacing(Spacing.MD)
        grid.setVerticalSpacing(Spacing.SM)
        self._supplier = EntitySearchInput(
            self, provider=self._presenter.supplier_options,
            placeholder="Buscar proveedor por nombre o código")
        self._supplier.selected.connect(self._on_supplier_selected)
        self._barcode = BarcodeInput(self)
        self._barcode.scanned.connect(self._on_scanned)
        self._mode = SearchableComboBox(placeholder="Modo")
        self._mode.set_options(MODE_OPTIONS)
        self._payment = SearchableComboBox(placeholder="Condición de pago")
        self._payment.set_options(PAYMENT_CONDITION_OPTIONS)
        self._payment_source = SearchableComboBox(placeholder="Fuente de pago")
        self._payment_source.set_options(PAYMENT_SOURCE_OPTIONS)

        grid.addWidget(QLabel("Proveedor"), 0, 0)
        grid.addWidget(self._supplier, 0, 1)
        grid.addWidget(QLabel("Escaneo"), 0, 2)
        grid.addWidget(self._barcode, 0, 3)
        grid.addWidget(QLabel("Modo"), 1, 0)
        grid.addWidget(self._mode, 1, 1)
        grid.addWidget(QLabel("Condición de pago"), 1, 2)
        grid.addWidget(self._payment, 1, 3)
        grid.addWidget(QLabel("Fuente de pago"), 2, 0)
        grid.addWidget(self._payment_source, 2, 1)
        body.addLayout(grid)

        self._cart_table = StandardTable(_CART_COLUMNS, self)
        body.addWidget(self._cart_table)

        line_actions = QHBoxLayout()
        add_btn = create_secondary_button(self, "Agregar producto")
        add_btn.clicked.connect(lambda: self._add_line())
        del_btn = create_secondary_button(self, "Quitar línea")
        del_btn.clicked.connect(self._remove_selected_line)
        line_actions.addWidget(add_btn)
        line_actions.addWidget(del_btn)
        line_actions.addStretch(1)
        self._totals_label = QLabel("")
        self._totals_label.setProperty("role", "muted")
        line_actions.addWidget(self._totals_label)
        body.addLayout(line_actions)

        doc_actions = QHBoxLayout()
        self._save_btn = create_primary_button(self, "Guardar compra")
        self._save_btn.clicked.connect(self._save)
        self._authorize_btn = create_warning_button(self, "Autorizar en caliente")
        self._authorize_btn.clicked.connect(self._authorize)
        self._confirm_btn = create_success_button(self, "Confirmar y recibir")
        self._confirm_btn.clicked.connect(self._confirm)
        self._reverse_btn = create_danger_button(self, "Reversar")
        self._reverse_btn.clicked.connect(self._reverse)
        for btn in (self._save_btn, self._authorize_btn, self._confirm_btn, self._reverse_btn):
            doc_actions.addWidget(btn)
        doc_actions.addStretch(1)
        self._status_label = QLabel("")
        self._status_label.setProperty("role", "muted")
        doc_actions.addWidget(self._status_label)
        body.addLayout(doc_actions)

        card.body().addLayout(body)
        return card

    # recent list -------------------------------------------------------------
    def _build_recent_card(self) -> QWidget:
        card = SectionCard(title="Compras directas recientes")
        body = QVBoxLayout()
        body.setSpacing(Spacing.SM)

        filters = QHBoxLayout()
        self._search = SearchInput(placeholder="Buscar por folio…")
        self._search.search_changed.connect(lambda *_: self.reload())
        self._status_filter = SearchableComboBox(placeholder="Todos los estados")
        self._status_filter.set_options([
            ("", "Todos"), ("DRAFT", "Borrador"),
            ("PENDING_AUTHORIZATION", "Pendiente de autorización"),
            ("CONFIRMED", "Confirmada"), ("RECEIVED", "Recibida"), ("REVERSED", "Reversada")])
        self._status_filter.selection_changed.connect(lambda *_: self.reload())
        filters.addWidget(self._search, stretch=1)
        filters.addWidget(self._status_filter)
        body.addLayout(filters)

        self._stack = QStackedWidget(self)
        self._list_table = StandardTable(_LIST_COLUMNS, self)
        self._list_table.clicked.connect(lambda *_: self._select_current())
        self._empty = create_state_widget(ViewState.EMPTY, self,
                                          message="Aún no hay compras directas")
        self._stack.addWidget(self._list_table)
        self._stack.addWidget(self._empty)
        body.addWidget(self._stack, stretch=1)

        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(refresh)
        body.addLayout(row)

        card.body().addLayout(body)
        return card

    # lifecycle ---------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            model = self._presenter.purchases(
                status=self._status_filter.current_id() or None,
                search=self._search.text().strip())
            self._list_table.load_rows(model.rows, row_ids=model.row_ids)
            self._stack.setCurrentWidget(self._list_table if model.rows else self._empty)
            self._loaded = True
        except Exception as exc:
            QMessageBox.warning(self, "Compra directa", f"No fue posible cargar:\n{exc}")

    # supplier / scan ---------------------------------------------------------
    def _on_supplier_selected(self, supplier_id) -> None:
        self._supplier_id = str(supplier_id) if supplier_id else None

    def _on_scanned(self, code: str) -> None:
        if code:
            self._add_line(prefill_product=code)

    # cart --------------------------------------------------------------------
    def _add_line(self, *, prefill_product: str | None = None) -> None:
        dialog = AddCartLineDialog(self)
        if prefill_product:
            dialog.prefill_product(prefill_product) if hasattr(
                dialog, "prefill_product") else None
        if not dialog.exec_():
            return
        line = dialog.line()
        if line is None:
            QMessageBox.warning(self, "Compra directa",
                                "Captura producto, cantidad y costo válidos.")
            return
        self._cart.append(line)
        self._render_cart()

    def _remove_selected_line(self) -> None:
        idx = self._cart_table.currentRow()
        if 0 <= idx < len(self._cart):
            self._cart.pop(idx)
            self._render_cart()

    def _render_cart(self) -> None:
        rows = [[ln.description, str(ln.quantity), money(ln.unit_cost), money(ln.tax),
                 money(ln.line_total())] for ln in self._cart]
        self._cart_table.load_rows(rows, row_ids=[str(i) for i in range(len(rows))])
        totals = self._presenter.totals(self._cart)
        self._totals_label.setText(
            f"Subtotal {totals['subtotal']}   IVA {totals['tax']}   Total {totals['total']}")

    # actions -----------------------------------------------------------------
    def _notify(self, ok: bool, message: str) -> None:
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Compra directa", message)

    def _save(self) -> None:
        if not self._supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        if not self._cart:
            self._notify(False, "Agrega al menos un producto.")
            return
        ok, msg, data = self._presenter.create(
            supplier_id=self._supplier_id, lines=self._cart,
            mode=self._mode.current_id() or "DIRECT_WITH_IMMEDIATE_RECEIPT",
            payment_condition=self._payment.current_id() or "IMMEDIATE_PAYMENT")
        if ok:
            self._current_id = data.get("entity_id")
            self._current_status = data.get("status")
            if data.get("requires_authorization"):
                msg += "\nRequiere autorización en caliente antes de confirmar."
        self._notify(ok, msg)
        if ok:
            self._cart = []
            self._render_cart()
            self._refresh_action_state()
            self.reload()

    def _authorize(self) -> None:
        if not self._current_id:
            self._notify(False, "Selecciona o guarda una compra primero.")
            return
        dialog = HotAuthorizationDialog(self)
        if not dialog.exec_():
            return
        if not dialog.reason():
            self._notify(False, "El motivo de autorización es obligatorio.")
            return
        ok, msg, data = self._presenter.authorize(self._current_id, dialog.reason())
        if ok:
            self._current_status = data.get("status")
        self._notify(ok, msg)
        self._refresh_action_state()
        self.reload()

    def _confirm(self) -> None:
        if not self._current_id:
            self._notify(False, "Selecciona o guarda una compra primero.")
            return
        source = self._payment_source.current_id() or None
        ok, msg, data = self._presenter.confirm(self._current_id, source)
        if ok:
            self._current_status = data.get("status")
        self._notify(ok, msg)
        self._refresh_action_state()
        self.reload()

    def _reverse(self) -> None:
        if not self._current_id:
            self._notify(False, "Selecciona una compra primero.")
            return
        dialog = ReverseReasonDialog(self)
        if not dialog.exec_():
            return
        if not dialog.reason():
            self._notify(False, "El motivo del reverso es obligatorio.")
            return
        ok, msg, data = self._presenter.reverse(self._current_id, dialog.reason())
        if ok:
            self._current_status = data.get("status")
        self._notify(ok, msg)
        self._refresh_action_state()
        self.reload()

    def _select_current(self) -> None:
        selected = self._list_table.selected_row_id()
        if not selected:
            return
        self._current_id = selected
        detail = self._presenter.detail(selected)
        self._current_status = detail.status if detail else None
        self._refresh_action_state()

    def _refresh_action_state(self) -> None:
        status = self._current_status
        self._authorize_btn.setEnabled(status == "PENDING_AUTHORIZATION")
        self._confirm_btn.setEnabled(status in ("DRAFT", "CONFIRMED"))
        self._reverse_btn.setEnabled(status in ("CONFIRMED", "RECEIVED"))
        self._status_label.setText(
            f"Compra actual: {status_es(status)}" if status else "Sin compra seleccionada")
