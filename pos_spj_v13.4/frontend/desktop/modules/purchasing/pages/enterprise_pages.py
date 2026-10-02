"""Enterprise procurement pages: requisitions, orders, invoices.

UI only: every read/mutation is delegated to the presenter. Backend pagination;
view states instead of misleading zeros; Design System components only.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    StandardTable,
    WorklistPage,
    create_primary_button,
    create_secondary_button,
    create_warning_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import (
    AwardDialog,
    InvoiceFormDialog,
    AcknowledgeOrderDialog,
    GenerateOrdersDialog,
    OrderFormDialog,
    QuoteCaptureDialog,
    ReasonDialog,
    ReceiveOrderDialog,
    RequisitionFormDialog,
    SupplierSelectionDialog,
)
from frontend.desktop.modules.purchasing.document_detail import (
    OrderDetailPanel, RequisitionDetailPanel, RfqDetailPanel, local_datetime_text,
)
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    INVOICE_STATUS_ES,
    ORDER_STATUS_ES,
    REQUISITION_STATUS_ES,
    RFQ_STATUS_ES,
    invoice_finance_text,
    invoice_status_es,
    match_result_es,
    money,
    status_filter as status_filter_options,
)


class _ListPageBase(WorklistPage):
    """Compras' worklist icon — behavior otherwise identical to WorklistPage
    (extracted here so Finanzas/RRHH can share it too; see MIGRATION_LOG.md)."""

    icon = Icons.PURCHASES


class RequisitionsPage(_ListPageBase):
    direct_purchase_requested = pyqtSignal(object)
    title = "Solicitudes de compra"
    subtitle = "Necesidades de reabasto: crear, enviar, aprobar."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Sucursal", "text"),
               ColumnSpec("Tipo", "text"), ColumnSpec("Prioridad", "text"),
               ColumnSpec("Estado", "status"), ColumnSpec("Fecha", "text")]
    status_filter = status_filter_options(REQUISITION_STATUS_ES, (
        "DRAFT", "PENDING_APPROVAL", "APPROVED", "PARTIALLY_SOURCED", "SOURCED", "REJECTED"))
    empty_message = "No hay solicitudes"

    def _create_detail_panel(self):
        self._detail = RequisitionDetailPanel(self, self._presenter.capabilities())
        self._detail.submit_button.clicked.connect(self._submit)
        self._detail.approve_button.clicked.connect(self._approve)
        self._detail.reject_button.clicked.connect(self._reject)
        self._detail.create_rfq_button.clicked.connect(self._create_rfq)
        self._detail.create_order_button.clicked.connect(self._create_order)
        self._detail.create_direct_button.clicked.connect(self._create_direct)
        return self._detail

    def _selection_changed(self):
        super()._selection_changed()
        requisition_id = self._selected()
        detail = self._presenter.requisition_detail(requisition_id) if requisition_id else None
        self._detail.load_detail(detail)

    def _build_actions(self):
        capabilities = self._presenter.capabilities()
        new = create_primary_button(self, "Nueva solicitud")
        new.setVisible(capabilities.requisition_create)
        new.clicked.connect(self._create)
        self.header.add_action(new)

    def _fetch(self):
        return self._presenter.requisitions(status=self._status_id() or None,
                                            search=self._search.text().strip(), page=self._page)

    def _default_branch_or_empty(self) -> str:
        """Sucursal de la sesión para PRESELECCIONAR, o vacío.

        `default_branch()` levanta `PermissionError` cuando la sesión no trae
        sucursal activa. Eso es correcto para una operación, pero aquí sólo se
        quiere una preselección: dejar que levante impediría abrir el diálogo y
        elegir la sucursal a mano, que es justo lo que este arreglo habilita.
        """
        try:
            return self._presenter.default_branch()
        except Exception:
            return ""

    def _create(self):
        dialog = RequisitionFormDialog(
            self, product_provider=self._presenter.product_options,
            empty_reason_provider=self._presenter.product_search_reason,
            branch_options=self._presenter.branch_options(),
            branch_id=self._default_branch_or_empty())
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
            detail.id, supplier_ids)
        self._notify(ok, msg)

    def _create_order(self):
        detail = self._selected_detail()
        if not detail:
            self._notify(False, "Selecciona una solicitud aprobada.")
            return
        result = open_order_form(self, self._presenter, source_requisition=detail)
        if result is not None:
            self._notify(*result)
            self.reload()

    def _create_direct(self):
        detail = self._selected_detail()
        if detail:
            self.direct_purchase_requested.emit(detail)


def open_acknowledge_order(parent, presenter, order_id):
    """Registra la confirmación del proveedor de una orden enviada. Devuelve
    ``(ok, mensaje)`` o ``None`` si se canceló."""
    detail = presenter.order_detail(order_id)
    if detail is None:
        return None
    dialog = AcknowledgeOrderDialog(
        parent, order_detail=detail,
        on_submit=lambda values, operation_id: presenter.acknowledge_order(
            order_id, operation_id=operation_id, **values))
    if not dialog.exec_() or dialog.result_data is None:
        return None
    _ok, message, data = dialog.result_data
    exceptions = data.get("exceptions") or []
    return True, message + (": " + "; ".join(exceptions) if exceptions else "")


def open_generate_orders(parent, presenter, rfq_id):
    """Abre «Generar órdenes de compra» para la adjudicación de ``rfq_id``.
    Devuelve ``(ok, mensaje)`` o ``None`` si se canceló o no hay adjudicación."""
    award = presenter.award_orders(rfq_id)
    if not award:
        return None
    options = presenter.warehouse_options(award.get("branch_id") or None)
    dialog = GenerateOrdersDialog(
        parent, award=award, warehouse_options=options,
        preselected_warehouse=presenter.preselected_warehouse(options),
        on_submit=lambda warehouse_id, operation_id: presenter.generate_orders_from_award(
            award["award_id"], warehouse_id, operation_id=operation_id))
    if not dialog.exec_() or dialog.result_data is None:
        return None
    _ok, message, data = dialog.result_data
    folios = ", ".join(o["document_number"] for o in data.get("orders", ())
                       if o.get("document_number"))
    return True, f"{message}{': ' + folios if folios else ''}"


def open_order_form(parent, presenter, *, source_requisition=None):
    """Abre «Nueva orden de compra» y la crea desde el propio diálogo.

    Antes ambas entradas exigían `default_warehouse()` ANTES de abrir: la sesión
    real nunca tiene almacén, así que en producción no se podía crear ninguna
    orden ("La sesión no tiene un almacén activo"). Ahora sucursal y almacén se
    eligen en el formulario. Devuelve `(ok, mensaje)` o `None` si se canceló."""
    def submit(values, operation_id):
        if source_requisition is not None:
            values = dict(values, requisition_id=source_requisition.id)
        return presenter.create_order(operation_id=operation_id, **values)

    try:
        branch = presenter.default_branch()
    except PermissionError:
        branch = ""     # sin sucursal en sesión: el usuario la elige
    dialog = OrderFormDialog(
        parent, source_requisition=source_requisition, branch_id=branch,
        supplier_provider=presenter.supplier_options,
        # Cable muerto histórico: sin `product_provider` el buscador devolvía
        # cero siempre, hubiera o no catálogo.
        product_provider=presenter.product_options,
        empty_reason_provider=presenter.product_search_reason,
        supplier_empty_reason=presenter.supplier_search_reason,
        branch_options=presenter.branch_options(),
        warehouse_provider=presenter.warehouse_options,
        preselect_warehouse=presenter.preselected_warehouse,
        profile_provider=presenter.purchase_profile,
        product_label_provider=presenter.product_label,
        origin_provider=presenter.supplier_origin_options,
        on_submit=submit)
    if not dialog.exec_() or dialog.result_data is None:
        return None
    _ok, message, data = dialog.result_data
    folio = data.get("document_number") or ""
    return True, f"{message}{' — ' + folio if folio else ''}"


class QuotationsPage(_ListPageBase):
    title = "Cotizaciones"
    subtitle = "Capturar lo que cotizó cada proveedor invitado y adjudicar."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Estado", "status"),
               ColumnSpec("Invitados", "text"), ColumnSpec("Cotizados", "text"),
               ColumnSpec("Adjudicada", "text"), ColumnSpec("Fecha", "text")]
    status_filter = status_filter_options(RFQ_STATUS_ES, ("DRAFT", "SENT", "CLOSED"))
    empty_message = "No hay RFQ"

    def _create_detail_panel(self):
        self._detail = RfqDetailPanel(self, self._presenter.capabilities())
        self._detail.capture_button.clicked.connect(self._capture_quote)
        self._detail.award_button.clicked.connect(self._award)
        self._detail.orders_button.clicked.connect(self._generate_orders)
        return self._detail

    def _selection_changed(self):
        super()._selection_changed()
        rfq_id = self._selected()
        detail = self._presenter.rfq_detail(rfq_id) if rfq_id else None
        self._detail.load_detail(detail, self._presenter.award_orders(rfq_id) if rfq_id else None)

    def _generate_orders(self, *_):
        rfq_id = self._selected()
        result = open_generate_orders(self, self._presenter, rfq_id) if rfq_id else None
        if result is not None:
            self._notify(*result)
            self._selection_changed()

    def _fetch(self):
        return self._presenter.rfqs(status=self._status_id() or None,
                                    search=self._search.text().strip(), page=self._page)

    def _capture_quote(self):
        rfq_id = self._selected()
        if not rfq_id:
            self._notify(False, "Selecciona una RFQ.")
            return
        detail = self._presenter.rfq_detail(rfq_id)
        if not detail or not detail.invitations:
            self._notify(False, "La RFQ no tiene proveedores invitados.")
            return
        invited = [(inv.supplier_id, inv.supplier_name) for inv in detail.invitations]
        dialog = QuoteCaptureDialog(
            self, invited_suppliers=invited,
            product_provider=self._presenter.product_options,
            empty_reason_provider=self._presenter.product_search_reason)
        if not dialog.exec_():
            return
        values = dialog.values()
        if not values["supplier_id"] or not values["lines"]:
            self._notify(False, "Selecciona proveedor y captura al menos una línea.")
            return
        ok, msg, _ = self._presenter.capture_quote(rfq_id=rfq_id, **values)
        self._notify(ok, msg)

    def _award(self):
        rfq_id = self._selected()
        if not rfq_id:
            self._notify(False, "Selecciona una RFQ.")
            return
        comparison = self._presenter.quote_comparison(rfq_id)
        if not comparison:
            self._notify(False, "La RFQ no tiene cotizaciones capturadas.")
            return
        dialog = AwardDialog(self, comparison_rows=comparison)
        if not dialog.exec_():
            return
        award_lines = dialog.award_lines()
        if not award_lines or not dialog.reason():
            self._notify(False, "Selecciona al menos una línea y captura la justificación.")
            return
        ok, msg, _ = self._presenter.award_quote(award_lines=award_lines, reason=dialog.reason())
        self._notify(ok, msg)
        if ok:
            # La adjudicación ya no termina aquí: se ofrece generar las órdenes
            # (una por proveedor) en el mismo paso; cancelar lo deja para después.
            result = open_generate_orders(self, self._presenter, rfq_id)
            if result is not None:
                self._notify(*result)
            self.reload()


class OrdersPage(_ListPageBase):
    title = "Órdenes de compra"
    subtitle = "Crear, aprobar, enviar, versionar y recibir."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Proveedor", "text"),
               ColumnSpec("Estado", "status"), ColumnSpec("Versión", "text"),
               ColumnSpec("Total", "text"), ColumnSpec("Fecha", "text")]
    status_filter = status_filter_options(ORDER_STATUS_ES, (
        "DRAFT", "PENDING_APPROVAL", "APPROVED", "SENT", "ACKNOWLEDGED",
        "PARTIALLY_RECEIVED", "RECEIVED"))
    empty_message = "No hay órdenes de compra"

    def _create_detail_panel(self):
        self._detail = OrderDetailPanel(self, self._presenter.capabilities())
        self._detail.approve_button.clicked.connect(self._approve)
        self._detail.send_button.clicked.connect(self._send)
        self._detail.acknowledge_button.clicked.connect(self._acknowledge)
        self._detail.receive_button.clicked.connect(self._receive)
        self._detail.change_button.clicked.connect(self._change)
        return self._detail

    def _selection_changed(self):
        super()._selection_changed()
        order_id = self._selected()
        self._detail.load_detail(self._presenter.order_detail(order_id) if order_id else None)

    def _build_actions(self):
        capabilities = self._presenter.capabilities()
        new = create_primary_button(self, "Nueva orden")
        new.setVisible(capabilities.order_create)
        new.clicked.connect(self._create)
        self.header.add_action(new)

    def _fetch(self):
        return self._presenter.orders(status=self._status_id() or None,
                                     search=self._search.text().strip(), page=self._page)

    def _create(self):
        result = open_order_form(self, self._presenter)
        if result is not None:
            self._notify(*result)
            self.reload()

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

    def _acknowledge(self, *_):
        oid = self._selected()
        if not oid:
            self._notify(False, "Selecciona una orden.")
            return
        result = open_acknowledge_order(self, self._presenter, oid)
        if result is not None:
            self._notify(*result)
            self.reload()

    def _receive(self):
        oid = self._selected()
        if not oid:
            self._notify(False, "Selecciona una orden.")
            return
        detail = self._presenter.order_detail(oid)
        dialog = ReceiveOrderDialog(self, order_detail=detail,
                                    profile_provider=self._presenter.purchase_profile)
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
    status_filter = status_filter_options(INVOICE_STATUS_ES, (
        "CAPTURED", "MATCHED", "WITH_DIFFERENCES", "APPROVED", "BLOCKED"))
    empty_message = "No hay facturas"

    _ACTIONS_BY_STATUS = {
        "CAPTURED": {"Conciliar"},
        "WITH_DIFFERENCES": {"Liberar diferencia"},
        "BLOCKED": {"Liberar diferencia"},
    }

    def _create_detail_panel(self):
        capabilities = self._presenter.capabilities()
        panel = QWidget(self); layout = QVBoxLayout(panel)
        self._invoice_commands = QWidget(panel)
        commands_row = QHBoxLayout(self._invoice_commands)
        commands_row.setContentsMargins(0, 0, 0, 0)
        self._match_button = create_secondary_button(panel, "Conciliar")
        self._match_button.setVisible(capabilities.invoice_match)
        self._match_button.clicked.connect(self._match)
        self._release_button = create_warning_button(panel, "Liberar diferencia")
        self._release_button.setVisible(capabilities.invoice_release_variance)
        self._release_button.clicked.connect(self._release)
        for b in (self._match_button, self._release_button):
            commands_row.addWidget(b)
        commands_row.addStretch(1)
        self._invoice_commands.setVisible(False)
        layout.addWidget(self._invoice_commands)
        self._invoice_summary = QLabel("Selecciona una factura", panel)
        self._invoice_summary.setWordWrap(True); layout.addWidget(self._invoice_summary)
        self._invoice_finance = QLabel("", panel)
        self._invoice_finance.setWordWrap(True)
        self._invoice_finance.setProperty("role", "muted")
        layout.addWidget(self._invoice_finance)
        self._invoice_lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Aceptado"), ColumnSpec("Facturado"),
            ColumnSpec("Precio pactado (neto)"), ColumnSpec("Precio factura"),
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
        if not invoice_id or not hasattr(self, "_invoice_lines"):
            if hasattr(self, "_invoice_commands"):
                self._invoice_commands.setVisible(False)
            return
        detail = self._presenter.invoice_detail(invoice_id)
        if not detail:
            self._invoice_commands.setVisible(False)
            return
        # Sólo las acciones que aplican al estado de ESTA factura (§9: nada de
        # botones grises deshabilitados).
        capabilities = self._presenter.capabilities()
        allowed = self._ACTIONS_BY_STATUS.get(str(detail.status or ""), set())
        self._match_button.setVisible(capabilities.invoice_match and "Conciliar" in allowed)
        self._release_button.setVisible(capabilities.invoice_release_variance
                                        and "Liberar diferencia" in allowed)
        self._invoice_commands.setVisible(bool(allowed))
        comparisons = {line["source_line_id"]: line for line in detail.comparison}
        rows = []
        for line in detail.lines:
            source_id = line.purchase_order_line_id or line.direct_purchase_line_id
            expected = comparisons.get(source_id, {})
            rows.append([line.product_name, str(expected.get("accepted_quantity", "0")),
                         line.invoiced_quantity,
                         money(expected["unit_price"]) if expected.get("unit_price") else "—",
                         money(line.unit_price), money(line.tax)])
        self._invoice_lines.load_rows(rows, row_ids=[str(i) for i in range(len(rows))])
        self._match_history.load_rows([[
            match_result_es(item.result), item.released_by_name or "—",
            item.notes or "—", local_datetime_text(item.created_at),
        ] for item in detail.matches],
            row_ids=[str(i) for i, _ in enumerate(detail.matches)])
        estado = invoice_status_es(detail.status)
        resultado = (match_result_es(detail.match_result) if detail.match_result
                     else "Sin conciliar")
        self._invoice_summary.setText(
            f"{detail.document_number} · Factura {detail.invoice_number} · "
            f"{detail.supplier_name} · Total {money(detail.total)} · {estado}"
            + ("" if resultado == estado else f" · {resultado}"))
        self._invoice_finance.setText(invoice_finance_text(detail))

    def _build_actions(self):
        capabilities = self._presenter.capabilities()
        new = create_primary_button(self, "Capturar factura")
        new.setVisible(capabilities.invoice_capture)
        new.clicked.connect(self._create)
        self.header.add_action(new)

    def _fetch(self):
        return self._presenter.invoices(status=self._status_id() or None,
                                       search=self._search.text().strip(), page=self._page)

    def _create(self):
        dialog = InvoiceFormDialog(
            self, document_provider=self._presenter.invoice_document_options,
            document_profile=self._presenter.invoice_document_profile,
            product_provider=self._presenter.product_options,
            empty_reason_provider=self._presenter.product_search_reason)
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
