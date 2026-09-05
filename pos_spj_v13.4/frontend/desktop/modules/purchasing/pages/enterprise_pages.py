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
    OrderFormDialog,
    QuoteCaptureDialog,
    ReasonDialog,
    ReceiveOrderDialog,
    RequisitionFormDialog,
    SupplierSelectionDialog,
)
from frontend.desktop.modules.purchasing.document_detail import (
    OrderDetailPanel, RequisitionDetailPanel, RfqDetailPanel,
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
    status_filter = [("", "Todos"), ("DRAFT", "Borrador"),
                     ("PENDING_APPROVAL", "Pendiente"), ("APPROVED", "Aprobada"),
                     ("REJECTED", "Rechazada")]
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

    def _create(self):
        dialog = RequisitionFormDialog(self, product_provider=self._presenter.product_options)
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
        try:
            warehouse_id = self._presenter.default_warehouse()
        except PermissionError as exc:
            self._notify(False, str(exc))
            return
        dialog = OrderFormDialog(
            self, source_requisition=detail,
            branch_id=self._presenter.default_branch(), warehouse_id=warehouse_id,
            supplier_provider=self._presenter.supplier_options,
            product_provider=self._presenter.product_options)
        if not dialog.exec_():
            return
        values = dialog.values()
        values["requisition_id"] = detail.id
        if not values["supplier_id"] or not values["lines"]:
            self._notify(False, "Captura proveedor y líneas con precio.")
            return
        ok, msg, _ = self._presenter.create_order(**values)
        self._notify(ok, msg)

    def _create_direct(self):
        detail = self._selected_detail()
        if detail:
            self.direct_purchase_requested.emit(detail)


class QuotationsPage(_ListPageBase):
    title = "Cotizaciones"
    subtitle = "Capturar lo que cotizó cada proveedor invitado y adjudicar."
    columns = [ColumnSpec("Folio", "text"), ColumnSpec("Estado", "status"),
               ColumnSpec("Invitados", "text"), ColumnSpec("Cotizados", "text"),
               ColumnSpec("Adjudicada", "text"), ColumnSpec("Fecha", "text")]
    status_filter = [("", "Todos"), ("DRAFT", "Borrador"), ("SENT", "Enviada"),
                     ("CLOSED", "Cerrada")]
    empty_message = "No hay RFQ"

    def _create_detail_panel(self):
        self._detail = RfqDetailPanel(self, self._presenter.capabilities())
        self._detail.capture_button.clicked.connect(self._capture_quote)
        self._detail.award_button.clicked.connect(self._award)
        return self._detail

    def _selection_changed(self):
        super()._selection_changed()
        rfq_id = self._selected()
        detail = self._presenter.rfq_detail(rfq_id) if rfq_id else None
        self._detail.load_detail(detail)

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
        dialog = QuoteCaptureDialog(self, invited_suppliers=invited,
                                    product_provider=self._presenter.product_options)
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
        self._detail = OrderDetailPanel(self, self._presenter.capabilities())
        self._detail.approve_button.clicked.connect(self._approve)
        self._detail.send_button.clicked.connect(self._send)
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
        if not invoice_id or not hasattr(self, "_invoice_lines"):
            if hasattr(self, "_invoice_commands"):
                self._invoice_commands.setVisible(False)
            return
        detail = self._presenter.invoice_detail(invoice_id)
        if not detail:
            self._invoice_commands.setVisible(False)
            return
        allowed = self._ACTIONS_BY_STATUS.get(str(detail.status or ""), set())
        self._match_button.setEnabled("Conciliar" in allowed)
        self._release_button.setEnabled("Liberar diferencia" in allowed)
        self._invoice_commands.setVisible(True)
        comparisons = {line["source_line_id"]: line for line in detail.comparison}
        rows = []
        for line in detail.lines:
            source_id = line.purchase_order_line_id or line.direct_purchase_line_id
            expected = comparisons.get(source_id, {})
            rows.append([line.product_id, str(expected.get("accepted_quantity", "0")),
                         line.invoiced_quantity, str(expected.get("unit_price", "—")),
                         line.unit_price, line.tax])
        self._invoice_lines.load_rows(rows, row_ids=[str(i) for i in range(len(rows))])
        self._match_history.load_rows([[
            item.result, item.released_by_user_id or "—",
            item.notes or "—", item.created_at,
        ] for item in detail.matches],
            row_ids=[str(i) for i, _ in enumerate(detail.matches)])
        self._invoice_summary.setText(
            f"{detail.document_number} · Factura {detail.invoice_number} · "
            f"{detail.status} · {detail.match_result or 'Sin conciliar'}")

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
            product_provider=self._presenter.product_options)
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
