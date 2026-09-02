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
        for step in self.STEPS:
            label = QLabel(f"○  {step}", self)
            label.setProperty("role", "muted")
            self._layout.addWidget(label)


class OrderDetailPanel(SectionCard):
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
        self.add(DocumentTimeline(self))

    def load_detail(self, detail) -> None:
        if not detail:
            self._summary.setText("No fue posible resolver el documento seleccionado.")
            self._lines.load_rows([])
            return
        get = detail.get if isinstance(detail, dict) else lambda key, default=None: getattr(detail, key, default)
        number = get("document_number", get("id", "—"))
        status = get("status", "—")
        supplier = get("supplier_id", "—")
        self._summary.setText(f"{number} · {status}\nProveedor: {supplier}")
        rows = []
        for line in get("lines", ()) or ():
            value = line.get if isinstance(line, dict) else lambda key, default=None: getattr(line, key, default)
            rows.append([
                value("product_id", "—"), value("ordered_quantity", value("quantity", "0")),
                value("unit_cost", value("unit_price", "0")), value("status", "—"),
            ])
        self._lines.load_rows(rows)
