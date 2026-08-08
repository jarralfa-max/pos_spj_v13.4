"""Master-detail and document timeline components for Procurement."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, SectionCard, StandardTable
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


class RequisitionDetailPanel(SectionCard):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Detalle de solicitud")
        self.setObjectName("procurementRequisitionDetail")
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

    def load_detail(self, detail) -> None:
        if not detail:
            self._summary.setText("Selecciona una solicitud para consultar su abastecimiento.")
            self._lines.load_rows([])
            self._related.load_rows([])
            self._timeline.set_events([])
            return
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
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Invitaciones y cotizaciones")
        self.setObjectName("procurementRfqDetail")
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

    def load_detail(self, detail) -> None:
        if not detail:
            self._summary.setText("Selecciona una RFQ para ver proveedores invitados y sus"
                                  " cotizaciones.")
            self._invitations.load_rows([])
            self._quotes.load_rows([])
            return
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
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Detalle y trazabilidad")
        self.setObjectName("procurementOrderDetail")
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

    def load_detail(self, detail) -> None:
        if not detail:
            self._summary.setText("Selecciona una orden para consultar líneas y trazabilidad.")
            self._lines.load_rows([])
            self._related.load_rows([])
            self._timeline.set_events([])
            return
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
