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
from frontend.desktop.themes.tokens import Spacing


class DocumentTimeline(QWidget):
    STEPS = ("PR", "RFQ", "Cotización", "Adjudicación", "OC / Directa",
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
        for label in self._labels:
            label.deleteLater()
        self._labels.clear()
        for event in events or ():
            get = event.get if isinstance(event, dict) else lambda key, default=None: getattr(event, key, default)
            action = str(get("action", "Actividad"))
            created = str(get("created_at", ""))[:19]
            actor = str(get("actor_user_id", "") or "Sistema")
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
            f"{detail.document_number} · {detail.status}\n"
            f"Solicitante: {detail.requested_by_name} · "
            f"Prioridad: {detail.priority}\n"
            f"Motivo: {detail.business_reason or 'Sin justificación'}")
        self._lines.load_rows([
            [line.product_id, line.quantity, line.estimated_unit_cost or "—",
             line.purchase_nature] for line in detail.lines])
        related = detail.related_documents
        self._related.load_rows([
            [document.get("document_number", "—"), document.get("document_type", "—"),
             document.get("status", "—")] for document in related],
            row_ids=[document.get("id", "") for document in related])
        self._timeline.set_events(detail.timeline)


class RfqDetailPanel(SectionCard):
    def __init__(self, parent=None, capabilities=None) -> None:
        super().__init__(parent, title="Invitaciones y cotizaciones")
        self.setObjectName("procurementRfqDetail")
        self.capture_button = create_secondary_button(self, "Capturar cotización")
        self.award_button = create_success_button(self, "Comparar y adjudicar")
        self._command_buttons = [self.capture_button, self.award_button]
        if capabilities is not None:
            self.capture_button.setVisible(capabilities.quote_capture)
            self.award_button.setVisible(capabilities.quote_award)
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

    def load_detail(self, detail) -> None:
        if not detail:
            self._commands.setVisible(False)
            self._summary.setText("Selecciona una RFQ para ver proveedores invitados y sus"
                                  " cotizaciones.")
            self._invitations.load_rows([])
            self._quotes.load_rows([])
            return
        allowed = set() if detail.awarded else {"Capturar cotización", "Comparar y adjudicar"}
        for button in self._command_buttons:
            button.setEnabled(button.text() in allowed)
        self._commands.setVisible(True)
        self._summary.setText(
            f"{detail.document_number} · {detail.status}\n"
            f"{'Adjudicada' if detail.awarded else 'Sin adjudicar'}")
        self._invitations.load_rows([
            [inv.supplier_name, inv.status, "Sí" if inv.has_quote else "No"]
            for inv in detail.invitations], row_ids=[inv.supplier_id for inv in detail.invitations])
        self._quotes.load_rows([
            [q.supplier_name, f"{q.total} {q.currency_code}", str(q.lead_time_days),
             str(q.line_count)] for q in detail.quotes],
            row_ids=[q.quote_id for q in detail.quotes])


class OrderDetailPanel(SectionCard):
    _ACTIONS_BY_STATUS = {
        "PENDING_APPROVAL": {"Aprobar"},
        "APPROVED": {"Enviar", "Nueva versión"},
        "SENT": {"Recibir", "Nueva versión"},
        "ACKNOWLEDGED": {"Recibir", "Nueva versión"},
        "PARTIALLY_RECEIVED": {"Recibir"},
    }

    def __init__(self, parent=None, capabilities=None) -> None:
        super().__init__(parent, title="Detalle y trazabilidad")
        self.setObjectName("procurementOrderDetail")
        self.approve_button = create_success_button(self, "Aprobar")
        self.send_button = create_secondary_button(self, "Enviar")
        self.receive_button = create_secondary_button(self, "Recibir")
        self.change_button = create_warning_button(self, "Nueva versión")
        self._command_buttons = [
            self.approve_button, self.send_button, self.receive_button, self.change_button,
        ]
        if capabilities is not None:
            self.approve_button.setVisible(capabilities.order_approve)
            self.send_button.setVisible(capabilities.order_send)
            self.receive_button.setVisible(capabilities.receipt_complete)
            self.change_button.setVisible(capabilities.order_change)
        self._commands = _command_bar(self, self._command_buttons)
        self.add(self._commands)
        self._summary = QLabel("Selecciona una orden para consultar líneas y trazabilidad.", self)
        self._summary.setWordWrap(True)
        self.add(self._summary)
        self._lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Costo", "numeric"), ColumnSpec("Recibido", "numeric"),
        ], self)
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
        self._summary.setText(
            f"{detail.document_number} · {detail.status} · v{detail.version}\n"
            f"Proveedor: {detail.supplier_name} · "
            f"Total: {detail.total} {detail.currency_code}")
        self._lines.load_rows([
            [line.product_id, line.ordered_quantity, line.unit_price or "—",
             line.received_quantity or "0"] for line in detail.lines])
        related = detail.related_documents
        self._related.load_rows([
            [document.get("document_number", "—"), document.get("document_type", "—"),
             document.get("status", "—")] for document in related],
            row_ids=[document.get("id", "") for document in related])
        self._timeline.set_events(detail.timeline)
