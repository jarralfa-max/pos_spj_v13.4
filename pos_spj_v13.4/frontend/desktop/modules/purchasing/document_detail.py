"""Master-detail and document timeline components for Procurement.

Each detail panel owns its document's command bar (business-action buttons
scoped to the selected document) — buttons live here, capability-gated at
construction time and enabled/disabled by document status in ``load_detail``.
The click handlers themselves stay on the owning page (they call the
presenter); panels only expose the buttons for the page to wire.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    SectionCard,
    StandardTable,
    create_secondary_button,
    create_success_button,
    create_warning_button,
)
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    document_status_es,
    document_type_es,
    local_datetime_text,
    money,
    priority_es,
    purchase_nature_es,
    requisition_status_es,
)
from frontend.desktop.themes.tokens import Spacing


#: Acciones de la bitácora de Compras en español (nunca el código técnico).
_TIMELINE_ACTIONS_ES = {
    "PURCHASE_REQUISITION_CREATED": "Solicitud creada",
    "PURCHASE_REQUISITION_SUBMITTED": "Solicitud enviada a aprobación",
    "PURCHASE_REQUISITION_APPROVED": "Solicitud aprobada",
    "PURCHASE_REQUISITION_REJECTED": "Solicitud rechazada",
    "RFQ_CREATED": "RFQ creada", "SUPPLIER_QUOTE_RECEIVED": "Cotización capturada",
    "SUPPLIER_QUOTE_AWARDED": "Cotización adjudicada",
    "PURCHASE_ORDER_CREATED": "Orden creada", "PURCHASE_ORDER_APPROVED": "Orden aprobada",
    "PURCHASE_ORDER_SENT": "Orden enviada al proveedor",
    "PURCHASE_ORDER_ACKNOWLEDGED": "Confirmada por el proveedor",
    "PURCHASE_ORDER_CHANGED": "Nueva versión de la orden",
    "PURCHASE_ORDER_CANCELLED": "Orden cancelada",
    "GOODS_RECEIPT_COMPLETED": "Mercancía recibida",
    "GOODS_RECEIPT_REVERSED": "Recepción reversada",
}


def timeline_action_es(code) -> str:
    code = str(code or "")
    if code in _TIMELINE_ACTIONS_ES:
        return _TIMELINE_ACTIONS_ES[code]
    return code.replace("_", " ").capitalize() if code else "Actividad"


class DocumentTimeline(QWidget):
    STEPS = ("Solicitud", "RFQ", "Cotización", "Adjudicación", "Orden / Compra directa",
             "Embarque", "Recepción", "Factura", "CxP", "Pago")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("procurementDocumentTimeline")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Spacing.XS)
        self._labels: list[QLabel] = []
        for step in self.STEPS:
            label = QLabel(f"○  {step}", self)
            label.setProperty("role", "muted")
            self._layout.addWidget(label)
            self._labels.append(label)

    def set_events(self, events) -> None:
        # Fuera del layout YA: `deleteLater` sólo actúa en la siguiente vuelta del
        # ciclo de eventos y, mientras, el historial anterior seguía visible.
        for label in self._labels:
            label.hide()
            self._layout.removeWidget(label)
            label.deleteLater()
        self._labels.clear()
        for event in events or ():
            get = event.get if isinstance(event, dict) else lambda key, default=None: getattr(event, key, default)
            action = timeline_action_es(get("action", ""))
            created = local_datetime_text(get("created_at", ""))
            actor = str(get("actor_name", "") or "Sistema")
            reason = str(get("reason", "") or "")
            text = f"●  {created} · {action} · {actor}"
            if reason:
                text += f"\n    {reason}"
            label = QLabel(text, self)
            label.setWordWrap(True)
            label.setProperty("role", "muted")
            self._layout.addWidget(label)
            self._labels.append(label)


def _command_bar(parent, buttons) -> QWidget:
    """A slim row of business-action buttons, shown above a document's
    summary. Hidden entirely (not just disabled) when nothing is selected."""
    bar = QWidget(parent)
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, Spacing.SM)
    row.setSpacing(Spacing.SM)
    for button in buttons:
        row.addWidget(button)
    row.addStretch(1)
    return bar


class RequisitionDetailPanel(SectionCard):
    _ACTIONS_BY_STATUS = {
        "DRAFT": {"Enviar"},
        "PENDING_APPROVAL": {"Aprobar", "Rechazar"},
        "APPROVED": {"Crear RFQ", "Crear orden", "Compra directa"},
    }

    def __init__(self, parent=None, capabilities=None) -> None:
        super().__init__(parent, title="Detalle de solicitud")
        self.setObjectName("procurementRequisitionDetail")
        self.submit_button = create_secondary_button(self, "Enviar")
        self.approve_button = create_success_button(self, "Aprobar")
        self.reject_button = create_warning_button(self, "Rechazar")
        self.create_rfq_button = create_secondary_button(self, "Crear RFQ")
        self.create_order_button = create_secondary_button(self, "Crear orden")
        self.create_direct_button = create_secondary_button(self, "Compra directa")
        self._command_buttons = [
            self.submit_button, self.approve_button, self.reject_button,
            self.create_rfq_button, self.create_order_button, self.create_direct_button,
        ]
        if capabilities is not None:
            self.submit_button.setVisible(capabilities.requisition_submit)
            self.approve_button.setVisible(capabilities.requisition_approve)
            self.reject_button.setVisible(capabilities.requisition_reject)
            self.create_rfq_button.setVisible(capabilities.rfq_create)
            self.create_order_button.setVisible(capabilities.order_create)
            self.create_direct_button.setVisible(capabilities.direct_create)
        self._commands = _command_bar(self, self._command_buttons)
        self.add(self._commands)
        self._summary = QLabel("Selecciona una solicitud para consultar su abastecimiento.", self)
        self._summary.setWordWrap(True)
        self.add(self._summary)
        self._lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Costo estimado", "numeric"), ColumnSpec("Naturaleza"),
        ], self)
        self._lines.setMinimumHeight(130)
        self._lines.setMaximumHeight(190)
        self.add(self._lines)
        self._related = StandardTable([
            ColumnSpec("Documento"), ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
        ], self)
        self._related.setMaximumHeight(130)
        self.add(self._related)
        self._timeline = DocumentTimeline(self)
        self.add(self._timeline)
        self._commands.setVisible(False)

    def load_detail(self, detail) -> None:
        if not detail:
            self._commands.setVisible(False)
            self._summary.setText("Selecciona una solicitud para consultar su abastecimiento.")
            self._lines.load_rows([])
            self._related.load_rows([])
            self._timeline.set_events([])
            return
        allowed = self._ACTIONS_BY_STATUS.get(str(detail.status or ""), set())
        for button in self._command_buttons:
            button.setEnabled(button.text() in allowed)
        self._commands.setVisible(True)
        self._summary.setText(
            f"{detail.document_number} · {requisition_status_es(detail.status)}\n"
            f"Solicitante: {detail.requested_by_name} · "
            f"Prioridad: {priority_es(detail.priority)}\n"
            f"Motivo: {detail.business_reason or 'Sin justificación'}")
        self._lines.load_rows([
            [line.product_name, line.quantity,
             money(line.estimated_unit_cost) if line.estimated_unit_cost else "—",
             purchase_nature_es(line.purchase_nature)] for line in detail.lines])
        related = detail.related_documents
        self._related.load_rows([
            [document.get("document_number", "—"),
             document_type_es(document.get("document_type")),
             document_status_es(document.get("document_type"), document.get("status"))]
            for document in related],
            row_ids=[document.get("id", "") for document in related])
        self._timeline.set_events(detail.timeline)


class RfqDetailPanel(SectionCard):
    def __init__(self, parent=None, capabilities=None) -> None:
        super().__init__(parent, title="Invitaciones y cotizaciones")
        self.setObjectName("procurementRfqDetail")
        self.capture_button = create_secondary_button(self, "Capturar cotización")
        self.award_button = create_success_button(self, "Comparar y adjudicar")
        self.orders_button = create_success_button(self, "Generar órdenes")
        self._command_buttons = [self.capture_button, self.award_button, self.orders_button]
        if capabilities is not None:
            self.capture_button.setVisible(capabilities.quote_capture)
            self.award_button.setVisible(capabilities.quote_award)
            self.orders_button.setVisible(capabilities.order_create)
        self._commands = _command_bar(self, self._command_buttons)
        self.add(self._commands)
        self._summary = QLabel("Selecciona una RFQ para ver proveedores invitados y sus"
                               " cotizaciones.", self)
        self._summary.setWordWrap(True)
        self.add(self._summary)
        self._invitations = StandardTable([
            ColumnSpec("Proveedor"), ColumnSpec("Estado", "status"), ColumnSpec("Cotizó"),
        ], self)
        self._invitations.setMaximumHeight(150)
        self.add(self._invitations)
        self._quotes = StandardTable([
            ColumnSpec("Proveedor"), ColumnSpec("Total", "numeric"),
            ColumnSpec("Plazo (días)", "numeric"), ColumnSpec("Líneas", "numeric"),
        ], self)
        self.add(self._quotes)
        self._commands.setVisible(False)

    def load_detail(self, detail, award_orders: dict | None = None) -> None:
        if not detail:
            self._commands.setVisible(False)
            self._summary.setText("Selecciona una RFQ para ver proveedores invitados y sus"
                                  " cotizaciones.")
            self._invitations.load_rows([])
            self._quotes.load_rows([])
            return
        from frontend.desktop.modules.purchasing.enterprise_view_models import (
            invitation_status_es,
            rfq_status_es,
        )
        suppliers = list((award_orders or {}).get("suppliers") or [])
        pending = [s for s in suppliers if not s["order_number"]]
        allowed = ({"Generar órdenes"} if pending else set()) if detail.awarded \
            else {"Capturar cotización", "Comparar y adjudicar"}
        for button in self._command_buttons:
            button.setEnabled(button.text() in allowed)
        self._commands.setVisible(True)
        lines = [f"{detail.document_number} · {rfq_status_es(detail.status)}",
                 "Adjudicada" if detail.awarded else "Sin adjudicar"]
        for s in suppliers:
            lines.append(f"{s['supplier_name']}: "
                         f"{s['order_number'] or 'orden por generar'}")
        self._summary.setText("\n".join(lines))
        self._invitations.load_rows([
            [inv.supplier_name, invitation_status_es(inv.status),
             "Sí" if inv.has_quote else "No"]
            for inv in detail.invitations], row_ids=[inv.supplier_id for inv in detail.invitations])
        self._quotes.load_rows([
            [q.supplier_name, f"{q.total} {q.currency_code}", str(q.lead_time_days),
             str(q.line_count)] for q in detail.quotes],
            row_ids=[q.quote_id for q in detail.quotes])


def _origin_text(snapshot_json) -> str:
    if not snapshot_json:
        return ""
    import json
    from backend.application.suppliers.queries.supplier_origin_query_service import (
        origin_display,
    )
    try:
        return origin_display(json.loads(snapshot_json))
    except (ValueError, TypeError):
        return ""


def order_summary_text(detail) -> str:
    """Encabezado de la orden en texto, con NOMBRES y estados en español. La
    confirmación del proveedor se muestra aparte de «Enviada» (§24)."""
    from frontend.desktop.modules.purchasing.enterprise_view_models import (
        delivery_method_es, order_status_es, payment_terms_es,
    )
    parts = [f"{detail.document_number} · {order_status_es(detail.status)} · v{detail.version}",
             f"Proveedor: {detail.supplier_name} · Comprador: {detail.buyer_name}",
             f"Destino: {detail.branch_name} / {detail.warehouse_name}",
             f"Total: {detail.total} {detail.currency_code}"
             + (f" · Tipo de cambio {detail.exchange_rate}" if detail.exchange_rate else "")]
    terms = []
    if detail.payment_terms:
        terms.append(f"Pago: {payment_terms_es(detail.payment_terms)}")
    if detail.delivery_method:
        terms.append(f"Entrega: {delivery_method_es(detail.delivery_method)}")
    origin = _origin_text(getattr(detail, "origin_address_snapshot", None))
    if origin:
        terms.append(f"Recoger en: {origin}")
    if detail.required_date:
        terms.append(f"Requerida: {detail.required_date}")
    if detail.promised_date:
        terms.append(f"Prometida: {detail.promised_date}")
    if terms:
        parts.append(" · ".join(terms))
    extra = [f"{label}: {value}" for label, value in (
        ("Dirección", detail.delivery_address), ("Centro de costo", detail.cost_center),
        ("Proyecto", detail.project_reference), ("Contrato", detail.contract_reference),
        ("Notas", detail.notes)) if value]
    if extra:
        parts.append(" · ".join(extra))
    if detail.confirmed_at:
        parts.append(f"Confirmada por el proveedor (ref. {detail.supplier_reference or '—'})"
                     f" el {local_datetime_text(detail.confirmed_at, date_only=True)}")
        if detail.confirmation_exceptions:
            parts.append("Excepciones: " + "; ".join(
                str(detail.confirmation_exceptions).splitlines()))
        if detail.confirmation_comments:
            parts.append(f"Comentarios: {detail.confirmation_comments}")
    elif str(detail.status) == "SENT":
        parts.append("Enviada — sin confirmación del proveedor")
    return "\n".join(parts)


class OrderDetailPanel(SectionCard):
    _ACTIONS_BY_STATUS = {
        "PENDING_APPROVAL": {"Aprobar"},
        "APPROVED": {"Enviar", "Nueva versión"},
        "SENT": {"Registrar confirmación", "Recibir", "Nueva versión"},
        "ACKNOWLEDGED": {"Recibir", "Nueva versión"},
        "PARTIALLY_RECEIVED": {"Recibir"},
    }

    def __init__(self, parent=None, capabilities=None) -> None:
        super().__init__(parent, title="Detalle y trazabilidad")
        self.setObjectName("procurementOrderDetail")
        self.approve_button = create_success_button(self, "Aprobar")
        self.send_button = create_secondary_button(self, "Enviar")
        self.acknowledge_button = create_secondary_button(self, "Registrar confirmación")
        self.receive_button = create_secondary_button(self, "Recibir")
        self.change_button = create_warning_button(self, "Nueva versión")
        self._command_buttons = [
            self.approve_button, self.send_button, self.acknowledge_button,
            self.receive_button, self.change_button,
        ]
        if capabilities is not None:
            self.approve_button.setVisible(capabilities.order_approve)
            self.send_button.setVisible(capabilities.order_send)
            self.acknowledge_button.setVisible(capabilities.order_acknowledge)
            self.receive_button.setVisible(capabilities.receipt_complete)
            self.change_button.setVisible(capabilities.order_change)
        self._commands = _command_bar(self, self._command_buttons)
        self.add(self._commands)
        self._summary = QLabel("Selecciona una orden para consultar líneas y trazabilidad.", self)
        self._summary.setWordWrap(True)
        self.add(self._summary)
        self._lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Cantidad compra", "numeric"),
            ColumnSpec("Cantidad inventario", "numeric"), ColumnSpec("Costo", "numeric"),
            ColumnSpec("Descuento", "numeric"), ColumnSpec("IVA", "numeric"),
            ColumnSpec("Subtotal", "numeric"), ColumnSpec("Confirmado", "numeric"),
            ColumnSpec("Recibido", "numeric"),
        ], self)
        self._lines.setMinimumHeight(130)
        self._lines.setMaximumHeight(190)
        self.add(self._lines)
        self._related = StandardTable([
            ColumnSpec("Documento"), ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
        ], self)
        self._related.setMaximumHeight(130)
        self.add(self._related)
        self._timeline = DocumentTimeline(self)
        self.add(self._timeline)
        self._commands.setVisible(False)

    def load_detail(self, detail) -> None:
        if not detail:
            self._commands.setVisible(False)
            self._summary.setText("Selecciona una orden para consultar líneas y trazabilidad.")
            self._lines.load_rows([])
            self._related.load_rows([])
            self._timeline.set_events([])
            return
        allowed = self._ACTIONS_BY_STATUS.get(str(detail.status or ""), set())
        for button in self._command_buttons:
            button.setEnabled(button.text() in allowed)
        self._commands.setVisible(True)
        self._summary.setText(order_summary_text(detail))
        self._lines.load_rows([
            [line.product_name, f"{line.ordered_quantity} {line.purchase_unit}".strip(),
             f"{line.inventory_quantity} {line.inventory_unit}".strip(),
             line.unit_price or "—", line.discount or "0", line.tax or "0",
             line.subtotal or "—",
             "—" if line.confirmed_quantity in (None, "") else line.confirmed_quantity,
             line.received_quantity or "0"] for line in detail.lines])
        related = detail.related_documents
        self._related.load_rows([
            [document.get("document_number", "—"),
             document_type_es(document.get("document_type")),
             document_status_es(document.get("document_type"), document.get("status"))]
            for document in related],
            row_ids=[document.get("id", "") for document in related])
        self._timeline.set_events(detail.timeline)
