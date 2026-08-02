"""Enterprise procurement pages: requisitions, orders, invoices.

UI only: every read/mutation is delegated to the presenter. Backend pagination;
view states instead of misleading zeros; Design System components only.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchInput,
    SearchableComboBox,
    StandardTable,
    ViewState,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
    create_success_button,
    create_warning_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
    InvoiceFormDialog,
    OrderFormDialog,
    ReasonDialog,
    ReceiveOrderDialog,
    RequisitionFormDialog,
    SupplierSelectionDialog,
)
from frontend.desktop.modules.purchasing.document_detail import (
    OrderDetailPanel, RequisitionDetailPanel,
)
from frontend.desktop.modules.purchasing.document_detail import OrderDetailPanel
from frontend.desktop.themes.tokens import Spacing


class _ListPageBase(QWidget):
    """Shared scaffold: header + filters + table + view states + pagination."""

    columns: list[ColumnSpec] = []
    title = ""
    subtitle = ""
    status_filter: list[tuple] = []
    empty_message = "Sin registros"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._page = 0
        self._total = 0
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(title=self.title, subtitle=self.subtitle,
                                 icon=Icons.PURCHASES, compact=True)
        layout.addWidget(self.header)
        self._build_actions()
        self._notice = QLabel("", self)
        self._notice.setObjectName("procurementInlineNotice")
        self._notice.setWordWrap(True)
        self._notice.hide()
        layout.addWidget(self._notice)

        filters = QHBoxLayout()
        self._search = SearchInput(placeholder="Buscar…")
        self._search.search_changed.connect(self._on_filter)
        self._status = SearchableComboBox(placeholder="Todos los estados")
        if self.status_filter:
            self._status.set_options(self.status_filter)
            self._status.selection_changed.connect(lambda *_: self._on_filter())
        filters.addWidget(self._search, stretch=1)
        if self.status_filter:
            filters.addWidget(self._status)
        layout.addLayout(filters)

        self._stack = QStackedWidget(self)
        self._table = StandardTable(self.columns, self)
        self._table.doubleClicked.connect(lambda *_: self._open_selected())
        self._empty = create_state_widget(ViewState.EMPTY, self, message=self.empty_message)
        self._stack.addWidget(self._table)
        self._stack.addWidget(self._empty)
        self._content = QSplitter(self)
        self._content.setObjectName("procurementMasterDetail")
        self._content.addWidget(self._stack)
        detail = self._create_detail_panel()
        if detail is not None:
            self._content.addWidget(detail)
            self._content.setStretchFactor(0, 3)
            self._content.setStretchFactor(1, 2)
        layout.addWidget(self._content, stretch=1)

        row = QHBoxLayout()
        self._build_row_actions(row)
        self._action_buttons = [row.itemAt(index).widget() for index in range(row.count())
                                if row.itemAt(index).widget() is not None]
        row.addStretch(1)
        self._prev = create_secondary_button(self, "Anterior")
        self._prev.clicked.connect(self._prev_page)
        self._next = create_secondary_button(self, "Siguiente")
        self._next.clicked.connect(self._next_page)
        self._page_label = QLabel("")
        self._page_label.setProperty("role", "muted")
        row.addWidget(self._page_label)
        row.addWidget(self._prev)
        row.addWidget(self._next)
        layout.addLayout(row)
        self._table.itemSelectionChanged.connect(self._selection_changed)
        self._selection_changed()

    # hooks -------------------------------------------------------------------
    def _build_actions(self) -> None:
        ...

    def _build_row_actions(self, row: QHBoxLayout) -> None:
        ...

    def _fetch(self):
        raise NotImplementedError

    def _create_detail_panel(self):
        return None

    def _selection_changed(self):
        selected = bool(self._selected())
        allowed = self._allowed_actions()
        for button in self._action_buttons:
            button.setEnabled(selected and (allowed is None or button.text() in allowed))

    def _allowed_actions(self):
        return None

    # lifecycle ---------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            model = self._fetch()
            self._total = model.total
            self._table.load_rows(model.rows, row_ids=model.row_ids)
            self._stack.setCurrentWidget(self._table if model.rows else self._empty)
            self._page_label.setText(self._page_text())
            self._loaded = True
        except Exception as exc:
            self._notice.setProperty("state", "ERROR")
            self._notice.setText(f"No fue posible cargar: {exc}")
            self._notice.show()

    def _on_filter(self) -> None:
        self._page = 0
        self.reload()

    def _status_id(self):
        return self._status.current_id() if self.status_filter else None

    def _page_text(self) -> str:
        start = self._page * 50 + 1 if self._total else 0
        end = min((self._page + 1) * 50, self._total)
        return f"{start}–{end} de {self._total}"

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.reload()

    def _next_page(self):
        if (self._page + 1) * 50 < self._total:
            self._page += 1
            self.reload()

    def _selected(self):
        return self._table.selected_row_id()

    def _notify(self, ok, message):
        self._notice.setProperty("state", "SUCCESS" if ok else "WARNING")
        self._notice.setText(message)
        self._notice.show()
        if ok:
            self.reload()

    def _open_selected(self):
        ...


class RequisitionsPage(_ListPageBase):
    direct_purchase_requested = pyqtSignal(object)
    title = "Solicitudes de compra"
    subtitle = "Necesidades de reabasto: crear, enviar, aprobar."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Sucursal", "text"),
               ColumnSpec("Tipo", "text"), ColumnSpec("Prioridad", "text"),
               ColumnSpec("Estado", "status"), ColumnSpec("Fecha", "text")]
    status_filter = [("", "Todos"), ("DRAFT", "Borrador"),
                     ("PENDING_APPROVAL", "Pendiente"), ("APPROVED", "Aprobada"),
                     ("REJECTED", "Rechazada")]
    empty_message = "No hay solicitudes"

<<<<<<< HEAD
    def _create_detail_panel(self):
        self._detail = RequisitionDetailPanel(self)
        return self._detail

    def _selection_changed(self):
        super()._selection_changed()
        requisition_id = self._selected()
        detail = self._presenter.requisition_detail(requisition_id) if requisition_id else None
        self._detail.load_detail(detail)

=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
    def _allowed_actions(self):
        row = self._table.currentRow()
        status = self._table.item(row, 4).text() if row >= 0 and self._table.item(row, 4) else ""
        return {
            "Borrador": {"Enviar"},
            "Pendiente de aprobación": {"Aprobar", "Rechazar"},
            "Pendiente": {"Aprobar", "Rechazar"},
<<<<<<< HEAD
            "Aprobada": {"Crear RFQ", "Crear orden", "Compra directa"},
=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        }.get(status, set())

    def _build_actions(self):
        capabilities = self._presenter.capabilities()
        new = create_primary_button(self, "Nueva solicitud")
<<<<<<< HEAD
        new.setVisible(capabilities.requisition_create)
=======
        new.setVisible(self._presenter.can("procurement.requisition.create"))
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        new.clicked.connect(self._create)
        self.header.add_action(new)

    def _build_row_actions(self, row):
        capabilities = self._presenter.capabilities()
        submit = create_secondary_button(self, "Enviar")
<<<<<<< HEAD
        submit.setVisible(capabilities.requisition_submit)
        submit.clicked.connect(self._submit)
        approve = create_success_button(self, "Aprobar")
        approve.setVisible(capabilities.requisition_approve)
        approve.clicked.connect(self._approve)
        reject = create_warning_button(self, "Rechazar")
        reject.setVisible(capabilities.requisition_reject)
=======
        submit.setVisible(self._presenter.can("procurement.requisition.submit"))
        submit.clicked.connect(self._submit)
        approve = create_success_button(self, "Aprobar")
        approve.setVisible(self._presenter.can("procurement.requisition.approve"))
        approve.clicked.connect(self._approve)
        reject = create_warning_button(self, "Rechazar")
        reject.setVisible(self._presenter.can("procurement.requisition.approve"))
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        reject.clicked.connect(self._reject)
        rfq = create_secondary_button(self, "Crear RFQ")
        rfq.setVisible(capabilities.rfq_create)
        rfq.clicked.connect(self._create_rfq)
        order = create_secondary_button(self, "Crear orden")
        order.setVisible(capabilities.order_create)
        order.clicked.connect(self._create_order)
        direct = create_secondary_button(self, "Compra directa")
        direct.setVisible(capabilities.direct_create)
        direct.clicked.connect(self._create_direct)
        for b in (submit, approve, reject, rfq, order, direct):
            row.addWidget(b)

    def _fetch(self):
        return self._presenter.requisitions(status=self._status_id() or None,
                                            search=self._search.text().strip(), page=self._page)

    def _create(self):
        dialog = RequisitionFormDialog(self)
        if not dialog.exec_():
            return
        values = dialog.values()
        if not values["lines"]:
            self._notify(False, "Agrega al menos un producto.")
            return
        ok, msg, _ = self._presenter.create_requisition(**values)
        self._notify(ok, msg)

    def start_create(self):
        self._create()

    def _submit(self):
        rid = self._selected()
        if not rid:
            self._notify(False, "Selecciona una solicitud.")
            return
        ok, msg, _ = self._presenter.submit_requisition(rid)
        self._notify(ok, msg)

    def _approve(self):
        rid = self._selected()
        if not rid:
            self._notify(False, "Selecciona una solicitud.")
            return
        ok, msg, _ = self._presenter.approve_requisition(rid, approve=True)
        self._notify(ok, msg)

    def _reject(self):
        rid = self._selected()
        if not rid:
            self._notify(False, "Selecciona una solicitud.")
            return
        dialog = ReasonDialog(self, title="Rechazar solicitud", ok_text="Rechazar")
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.approve_requisition(rid, approve=False,
                                                        reason=dialog.reason())
        self._notify(ok, msg)

    def _selected_detail(self):
        requisition_id = self._selected()
        return self._presenter.requisition_detail(requisition_id) if requisition_id else None

    def _create_rfq(self):
        detail = self._selected_detail()
        if not detail:
            self._notify(False, "Selecciona una solicitud aprobada.")
            return
        dialog = SupplierSelectionDialog(self, provider=self._presenter.supplier_options)
        if not dialog.exec_():
            return
        supplier_ids = dialog.supplier_ids()
        if not supplier_ids:
            self._notify(False, "Selecciona al menos un proveedor.")
            return
        ok, msg, _ = self._presenter.create_rfq_from_requisition(
            detail["id"], supplier_ids)
        self._notify(ok, msg)

    def _create_order(self):
        detail = self._selected_detail()
        if not detail:
            self._notify(False, "Selecciona una solicitud aprobada.")
            return
        try:
            warehouse_id = self._presenter.default_warehouse()
        except PermissionError as exc:
            self._notify(False, str(exc))
            return
        dialog = OrderFormDialog(
            self, source_requisition=detail,
            branch_id=self._presenter.default_branch(), warehouse_id=warehouse_id,
            supplier_provider=self._presenter.supplier_options)
        if not dialog.exec_():
            return
        values = dialog.values()
        values["requisition_id"] = detail["id"]
        if not values["supplier_id"] or not values["lines"]:
            self._notify(False, "Captura proveedor y líneas con precio.")
            return
        ok, msg, _ = self._presenter.create_order(**values)
        self._notify(ok, msg)

    def _create_direct(self):
        detail = self._selected_detail()
        if detail:
            self.direct_purchase_requested.emit(detail)


class OrdersPage(_ListPageBase):
    title = "Órdenes de compra"
    subtitle = "Crear, aprobar, enviar, versionar y recibir."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Proveedor", "text"),
               ColumnSpec("Estado", "status"), ColumnSpec("Versión", "text"),
               ColumnSpec("Total", "text"), ColumnSpec("Fecha", "text")]
    status_filter = [("", "Todos"), ("DRAFT", "Borrador"),
                     ("PENDING_APPROVAL", "Pendiente"), ("APPROVED", "Aprobada"),
                     ("SENT", "Enviada"), ("PARTIALLY_RECEIVED", "Recibida parcial"),
                     ("RECEIVED", "Recibida")]
    empty_message = "No hay órdenes de compra"

    def _create_detail_panel(self):
        self._detail = OrderDetailPanel(self)
        return self._detail

    def _allowed_actions(self):
        row = self._table.currentRow()
        status = self._table.item(row, 2).text() if row >= 0 and self._table.item(row, 2) else ""
        return {
            "Pendiente": {"Aprobar"},
            "Aprobada": {"Enviar", "Nueva versión"},
            "Enviada": {"Recibir", "Nueva versión"},
            "Confirmada": {"Recibir", "Nueva versión"},
            "Recibida parcial": {"Recibir"},
        }.get(status, set())

    def _selection_changed(self):
        super()._selection_changed()
        order_id = self._selected()
        self._detail.load_detail(self._presenter.order_detail(order_id) if order_id else None)

    def _build_actions(self):
        capabilities = self._presenter.capabilities()
        new = create_primary_button(self, "Nueva orden")
<<<<<<< HEAD
        new.setVisible(capabilities.order_create)
=======
        new.setVisible(self._presenter.can("procurement.purchase_order.create"))
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        new.clicked.connect(self._create)
        self.header.add_action(new)

    def _build_row_actions(self, row):
        capabilities = self._presenter.capabilities()
        approve = create_success_button(self, "Aprobar")
<<<<<<< HEAD
        approve.setVisible(capabilities.order_approve)
        approve.clicked.connect(self._approve)
        send = create_secondary_button(self, "Enviar")
        send.setVisible(capabilities.order_send)
        send.clicked.connect(self._send)
        receive = create_secondary_button(self, "Recibir")
        receive.setVisible(capabilities.receipt_complete)
        receive.clicked.connect(self._receive)
        change = create_warning_button(self, "Nueva versión")
        change.setVisible(capabilities.order_change)
=======
        approve.setVisible(self._presenter.can("procurement.purchase_order.approve"))
        approve.clicked.connect(self._approve)
        send = create_secondary_button(self, "Enviar")
        send.setVisible(self._presenter.can("procurement.purchase_order.send"))
        send.clicked.connect(self._send)
        receive = create_secondary_button(self, "Recibir")
        receive.setVisible(self._presenter.can("logistics.shipment.receive"))
        receive.clicked.connect(self._receive)
        change = create_warning_button(self, "Nueva versión")
        change.setVisible(self._presenter.can("procurement.purchase_order.change"))
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        change.clicked.connect(self._change)
        for b in (approve, send, receive, change):
            row.addWidget(b)

    def _fetch(self):
        return self._presenter.orders(status=self._status_id() or None,
                                     search=self._search.text().strip(), page=self._page)

    def _create(self):
        try:
            warehouse_id = self._presenter.default_warehouse()
        except PermissionError as exc:
            self._notify(False, str(exc))
            return
        dialog = OrderFormDialog(
            self, branch_id=self._presenter.default_branch(),
            warehouse_id=warehouse_id,
            supplier_provider=self._presenter.supplier_options)
        if not dialog.exec_():
            return
        values = dialog.values()
        if not values["supplier_id"] or not values["lines"]:
            self._notify(False, "Captura proveedor y al menos un producto.")
            return
        ok, msg, _ = self._presenter.create_order(**values)
        self._notify(ok, msg)

    def start_create(self):
        self._create()

    def _approve(self):
        oid = self._selected()
        if not oid:
            self._notify(False, "Selecciona una orden.")
            return
        ok, msg, _ = self._presenter.approve_order(oid)
        self._notify(ok, msg)

    def _send(self):
        oid = self._selected()
        if not oid:
            self._notify(False, "Selecciona una orden.")
            return
        ok, msg, _ = self._presenter.send_order(oid)
        self._notify(ok, msg)

    def _receive(self):
        oid = self._selected()
        if not oid:
            self._notify(False, "Selecciona una orden.")
            return
        detail = self._presenter.order_detail(oid)
        dialog = ReceiveOrderDialog(self, order_detail=detail)
        if not dialog.exec_():
            return
        lines = dialog.receipt_lines()
        if not lines:
            self._notify(False, "Captura cantidades recibidas.")
            return
        ok, msg, _ = self._presenter.receive_order(oid, receipt_lines=lines)
        self._notify(ok, msg)

    def _change(self):
        oid = self._selected()
        if not oid:
            self._notify(False, "Selecciona una orden.")
            return
        dialog = ReasonDialog(self, title="Nueva versión de la orden", ok_text="Versionar")
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.change_order(oid, reason=dialog.reason())
        self._notify(ok, msg)


class InvoicesPage(_ListPageBase):
    title = "Facturas de proveedor"
    subtitle = "Capturar, conciliar (3 vías) y liberar diferencias."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Proveedor", "text"),
               ColumnSpec("Factura", "text"), ColumnSpec("Total", "text"),
               ColumnSpec("Estado", "status"), ColumnSpec("Conciliación", "status"),
               ColumnSpec("Fecha", "text")]
    status_filter = [("", "Todos"), ("CAPTURED", "Capturada"), ("MATCHED", "Conciliada"),
                     ("WITH_DIFFERENCES", "Con diferencias"), ("APPROVED", "Aprobada"),
                     ("BLOCKED", "Bloqueada")]
    empty_message = "No hay facturas"

<<<<<<< HEAD
    def _create_detail_panel(self):
        panel = QWidget(self); layout = QVBoxLayout(panel)
        self._invoice_summary = QLabel("Selecciona una factura", panel)
        self._invoice_summary.setWordWrap(True); layout.addWidget(self._invoice_summary)
        self._invoice_lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Aceptado"), ColumnSpec("Facturado"),
            ColumnSpec("Precio acordado"), ColumnSpec("Precio factura"),
            ColumnSpec("Impuesto"),
        ], panel)
        layout.addWidget(self._invoice_lines)
        self._match_history = StandardTable([
            ColumnSpec("Resultado", "status"), ColumnSpec("Liberó"),
            ColumnSpec("Notas"), ColumnSpec("Fecha")], panel)
        layout.addWidget(self._match_history)
        return panel

    def _selection_changed(self):
        super()._selection_changed()
        invoice_id = self._selected()
        if not invoice_id or not hasattr(self, "_invoice_lines"): return
        detail = self._presenter.invoice_detail(invoice_id)
        if not detail: return
        comparisons = {line["source_line_id"]: line for line in detail.get("comparison", ())}
        rows = []
        for line in detail.get("lines", ()):
            source_id = line.get("purchase_order_line_id") or line.get("direct_purchase_line_id")
            expected = comparisons.get(source_id, {})
            rows.append([line["product_id"], str(expected.get("accepted_quantity", "0")),
                         line["invoiced_quantity"], str(expected.get("unit_price", "—")),
                         line["unit_price"], line["tax"]])
        self._invoice_lines.load_rows(rows, row_ids=[str(i) for i in range(len(rows))])
        self._match_history.load_rows([[
            item["result"], item.get("released_by_user_id") or "—",
            item.get("notes") or "—", item["created_at"],
        ] for item in detail.get("matches", ())],
            row_ids=[str(i) for i, _ in enumerate(detail.get("matches", ()))])
        self._invoice_summary.setText(
            f"{detail['document_number']} · Factura {detail['invoice_number']} · "
            f"{detail['status']} · {detail.get('match_result') or 'Sin conciliar'}")

=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
    def _allowed_actions(self):
        row = self._table.currentRow()
        status = self._table.item(row, 4).text() if row >= 0 and self._table.item(row, 4) else ""
        return {
            "Capturada": {"Conciliar"},
            "Con diferencias": {"Liberar diferencia"},
            "Bloqueada": {"Liberar diferencia"},
        }.get(status, set())

    def _build_actions(self):
        capabilities = self._presenter.capabilities()
        new = create_primary_button(self, "Capturar factura")
<<<<<<< HEAD
        new.setVisible(capabilities.invoice_capture)
=======
        new.setVisible(self._presenter.can("procurement.invoice.capture"))
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        new.clicked.connect(self._create)
        self.header.add_action(new)

    def _build_row_actions(self, row):
        capabilities = self._presenter.capabilities()
        match = create_secondary_button(self, "Conciliar")
<<<<<<< HEAD
        match.setVisible(capabilities.invoice_match)
        match.clicked.connect(self._match)
        release = create_warning_button(self, "Liberar diferencia")
        release.setVisible(capabilities.invoice_release_variance)
=======
        match.setVisible(self._presenter.can("procurement.invoice.match"))
        match.clicked.connect(self._match)
        release = create_warning_button(self, "Liberar diferencia")
        release.setVisible(self._presenter.can("procurement.invoice.release_difference"))
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
        release.clicked.connect(self._release)
        for b in (match, release):
            row.addWidget(b)

    def _fetch(self):
        return self._presenter.invoices(status=self._status_id() or None,
                                       search=self._search.text().strip(), page=self._page)

    def _create(self):
        dialog = InvoiceFormDialog(
            self, document_provider=self._presenter.invoice_document_options,
            document_profile=self._presenter.invoice_document_profile)
        if not dialog.exec_():
            return
        values = dialog.values()
        if not values["supplier_id"] or not values["invoice_number"]:
            self._notify(False, "Captura proveedor y número de factura.")
            return
        ok, msg, _ = self._presenter.capture_invoice(**values)
        self._notify(ok, msg)

    def start_create(self):
        self._create()

    def _match(self):
        iid = self._selected()
        if not iid:
            self._notify(False, "Selecciona una factura.")
            return
        ok, msg, _ = self._presenter.match_invoice(iid)
        self._notify(ok, msg)

    def _release(self):
        iid = self._selected()
        if not iid:
            self._notify(False, "Selecciona una factura.")
            return
        dialog = ReasonDialog(self, title="Liberar diferencia", ok_text="Liberar")
        if not dialog.exec_():
            return
        ok, msg, _ = self._presenter.release_variance(iid, reason=dialog.reason())
        self._notify(ok, msg)
