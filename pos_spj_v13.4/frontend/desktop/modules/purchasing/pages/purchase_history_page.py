"""Read-only master-detail view of Inventory-owned receipts related to Procurement."""

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, SectionCard, StandardTable, create_secondary_button
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class PurchaseHistoryPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter; self._loaded = False
        layout = QVBoxLayout(self); layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        self.header = PageHeader(title="Recepciones relacionadas",
            subtitle="Inventario conserva la recepción física; Compras consulta aceptados, rechazos y diferencias.",
            icon=Icons.PURCHASES, compact=True)
        refresh = create_secondary_button(self, "Actualizar"); refresh.clicked.connect(self.reload)
        self.header.add_action(refresh); layout.addWidget(self.header)
        self._notice = QLabel("", self); self._notice.setWordWrap(True); self._notice.hide(); layout.addWidget(self._notice)
        split = QSplitter(self); layout.addWidget(split, stretch=1)
        master = SectionCard(title="Recepciones")
        self._table = StandardTable([
            ColumnSpec("Folio"), ColumnSpec("Proveedor"), ColumnSpec("Estado", "status"),
            ColumnSpec("Recibido"), ColumnSpec("Aceptado"), ColumnSpec("Rechazado"),
            ColumnSpec("Diferencias")], self)
        self._table.itemSelectionChanged.connect(self._select)
        master.body().addWidget(self._table); split.addWidget(master)
        detail = SectionCard(title="Detalle y conciliación")
        self._summary = QLabel("Selecciona una recepción", self); self._summary.setWordWrap(True)
        detail.body().addWidget(self._summary)
        self._lines = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("Ordenado"), ColumnSpec("Recibido"),
            ColumnSpec("Aceptado"), ColumnSpec("Rechazado"), ColumnSpec("Lote")], self)
        detail.body().addWidget(self._lines)
        self._differences = StandardTable([
            ColumnSpec("Tipo", "status"), ColumnSpec("Esperado"), ColumnSpec("Real"), ColumnSpec("Motivo")], self)
        detail.body().addWidget(self._differences)
        self._invoices = StandardTable([
            ColumnSpec("Factura"), ColumnSpec("Número"), ColumnSpec("Estado", "status"),
            ColumnSpec("Conciliación", "status"), ColumnSpec("Total")], self)
        detail.body().addWidget(self._invoices); split.addWidget(detail)
        split.setStretchFactor(0, 2); split.setStretchFactor(1, 3)

    def ensure_loaded(self):
        if not self._loaded: self.reload()

    def reload(self):
        try:
            rows = self._presenter.receipts()
            self._table.load_rows([[
                row["document_number"], row["supplier_name"], row["status"],
                str(row["received"]), str(row["accepted"]), str(row["rejected"]),
                str(row["differences"]),
            ] for row in rows], row_ids=[row["id"] for row in rows])
            self._loaded = True
        except Exception as exc:
            self._notice.setText(str(exc)); self._notice.setProperty("state", "ERROR"); self._notice.show()

    def _select(self):
        receipt_id = self._table.selected_row_id()
        if not receipt_id: return
        row = self._presenter.receipt_detail(receipt_id)
        if not row: return
        self._summary.setText(f"{row['document_number']} · {row['status']} · Almacén {row['warehouse_id']}")
        self._lines.load_rows([[
            item["product_id"], item["ordered_quantity"], item["received_quantity"],
            item["accepted_quantity"], item["rejected_quantity"], item.get("lot") or "—",
        ] for item in row["lines"]], row_ids=[item["id"] for item in row["lines"]])
        self._differences.load_rows([[
            item["discrepancy_type"], item["expected"], item["actual"], item["reason"] or "—",
        ] for item in row["differences"]], row_ids=[str(i) for i, _ in enumerate(row["differences"])])
        self._invoices.load_rows([[
            item["document_number"], item["invoice_number"], item["status"],
            item.get("match_result") or "—", item["total"],
        ] for item in row["invoices"]], row_ids=[item["id"] for item in row["invoices"]])
