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
            f"{detail.get('document_number', '—')} · {detail.get('status', '—')}\n"
            f"Solicitante: {detail.get('requested_by_user_id', '—')} · "
            f"Prioridad: {detail.get('priority', '—')}\n"
            f"Motivo: {detail.get('business_reason') or 'Sin justificación'}")
        self._lines.load_rows([
            [line.get("product_id", "—"), line.get("quantity", "0"),
             line.get("estimated_unit_cost") or "—", line.get("purchase_nature", "—")]
            for line in detail.get("lines", ())])
        related = detail.get("related_documents", ())
        self._related.load_rows([
            [document.get("document_number", "—"), document.get("document_type", "—"),
             document.get("status", "—")] for document in related],
            row_ids=[document.get("id", "") for document in related])
        self._timeline.set_events(detail.get("timeline", ()))

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Detalle y trazabilidad")
        self.setObjectName("procurementOrderDetail")
        self._summary = QLabel("Selecciona una orden para consultar líneas y trazabilidad.", self)
        self._summary.setWordWrap(True)
        self.add(self._summary)
        self._lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Costo", "numeric"), ColumnSpec("Estado", "status"),
        ], self)
        self._lines.setMaximumHeight(220)
        self.add(self._lines)
        self._timeline = DocumentTimeline(self)
        self.add(self._timeline)
    def load_detail(self, detail) -> None:
        if not detail:
            self._timeline.set_events([])
