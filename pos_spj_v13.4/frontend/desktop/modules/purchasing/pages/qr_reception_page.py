"""QR reception page (PUR-13 step 2c) — migrated from the monolith's QR tab.

Subtabs: Generar etiqueta · Asignar · Recibir · Histórico. UI only; every
read/mutation is delegated to the presenter (no SQL, no direct inventory writes).
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    DateInput,
    PageHeader,
    SearchableComboBox,
    StandardLineEdit,
    StandardTable,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.purchasing.dialogs.enterprise_dialogs import _LinesEditor
from frontend.desktop.themes.tokens import Spacing

_PAYMENT = [("liquidado", "Liquidado"), ("crédito", "Crédito"), ("parcial", "Parcial")]


class QrReceptionPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("qrReceptionPage")
        self._presenter = presenter
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Recepción con QR",
            subtitle="Genera etiquetas, asigna contenedores, recibe y consulta el histórico.",
            icon=Icons.PURCHASES, compact=True))

        self._tabs = QTabWidget(self)
        self._tabs.setObjectName("qrSubtabs")
        self._tabs.addTab(self._build_generate(), "Generar etiqueta")
        self._tabs.addTab(self._build_assign(), "Asignar")
        self._tabs.addTab(self._build_receive(), "Recibir")
        self._tabs.addTab(self._build_history(), "Histórico")
        self._tabs.currentChanged.connect(lambda _i: self.reload())
        layout.addWidget(self._tabs, stretch=1)

    # generate ----------------------------------------------------------------
    def _build_generate(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self._gen_desc = StandardLineEdit(w)
        self._gen_desc.setPlaceholderText("Descripción del contenedor")
        gen_btn = create_primary_button(w, "Generar etiqueta")
        gen_btn.clicked.connect(self._generate)
        row.addWidget(QLabel("Descripción"))
        row.addWidget(self._gen_desc, stretch=1)
        row.addWidget(gen_btn)
        lay.addLayout(row)
        self._gen_result = QLabel("")
        self._gen_result.setProperty("role", "muted")
        lay.addWidget(self._gen_result)
        lay.addStretch(1)
        return w

    def _generate(self) -> None:
        ok, msg, data = self._presenter.generate_qr_label(
            description=self._gen_desc.text().strip())
        if ok:
            self._gen_result.setText(f"Etiqueta QR: {data.get('uuid_qr','')}")
            self._gen_desc.clear()
        else:
            QMessageBox.warning(self, "Recepción QR", msg)

    # assign ------------------------------------------------------------------
    def _build_assign(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        self._assign_table = StandardTable(
            [ColumnSpec("Código", "text"), ColumnSpec("Descripción", "text"),
             ColumnSpec("Estado", "status")], w)
        lay.addWidget(self._assign_table)
        form = QHBoxLayout()
        self._assign_supplier = StandardLineEdit(w)
        self._assign_supplier.setPlaceholderText("Proveedor (ID)")
        self._assign_payment = SearchableComboBox(placeholder="Condición de pago")
        self._assign_payment.set_options(_PAYMENT)
        form.addWidget(QLabel("Proveedor"))
        form.addWidget(self._assign_supplier, stretch=1)
        form.addWidget(self._assign_payment)
        lay.addLayout(form)
        self._assign_lines = _LinesEditor(w, with_price=True)
        lay.addWidget(self._assign_lines)
        btn = create_success_button(w, "Asignar contenedor")
        btn.clicked.connect(self._assign)
        lay.addWidget(btn)
        return w

    def _assign(self) -> None:
        uuid_qr = self._assign_table.selected_row_id()
        if not uuid_qr:
            QMessageBox.warning(self, "Recepción QR", "Selecciona un contenedor.")
            return
        supplier = self._assign_supplier.text().strip()
        items = [{"product_id": ln["product_id"], "cantidad": ln["quantity"],
                  "costo_unitario": ln.get("unit_price", "0")}
                 for ln in self._assign_lines.lines()]
        if not supplier or not items:
            QMessageBox.warning(self, "Recepción QR", "Captura proveedor y productos.")
            return
        ok, msg, _ = self._presenter.assign_qr(
            uuid_qr=uuid_qr, supplier_id=supplier, items=items,
            payment_condition=self._assign_payment.current_id() or "liquidado")
        QMessageBox.information(self, "Recepción QR", msg) if ok else \
            QMessageBox.warning(self, "Recepción QR", msg)
        if ok:
            self.reload()

    # receive -----------------------------------------------------------------
    def _build_receive(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        self._receive_table = StandardTable(
            [ColumnSpec("Código", "text"), ColumnSpec("Proveedor", "text"),
             ColumnSpec("Estado", "status")], w)
        lay.addWidget(self._receive_table)
        self._receive_lines = _LinesEditor(w, with_price=True)
        lay.addWidget(self._receive_lines)
        btn = create_success_button(w, "Registrar recepción")
        btn.clicked.connect(self._receive)
        lay.addWidget(btn)
        return w

    def _receive(self) -> None:
        uuid_qr = self._receive_table.selected_row_id()
        if not uuid_qr:
            QMessageBox.warning(self, "Recepción QR", "Selecciona un contenedor pendiente.")
            return
        items = [{"product_id": ln["product_id"], "quantity": ln["quantity"],
                  "unit_cost": ln.get("unit_price", "0")}
                 for ln in self._receive_lines.lines()]
        if not items:
            QMessageBox.warning(self, "Recepción QR", "Captura los productos recibidos.")
            return
        ok, msg, _ = self._presenter.complete_qr_reception(uuid_qr=uuid_qr, items=items)
        QMessageBox.information(self, "Recepción QR", msg) if ok else \
            QMessageBox.warning(self, "Recepción QR", msg)
        if ok:
            self.reload()

    # history -----------------------------------------------------------------
    def _build_history(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        filters = QHBoxLayout()
        self._hist_from = DateInput(w)
        self._hist_to = DateInput(w)
        go = create_secondary_button(w, "Consultar")
        go.clicked.connect(self._load_history)
        filters.addWidget(QLabel("Desde"))
        filters.addWidget(self._hist_from)
        filters.addWidget(QLabel("Hasta"))
        filters.addWidget(self._hist_to)
        filters.addWidget(go)
        filters.addStretch(1)
        lay.addLayout(filters)
        self._hist_table = StandardTable(
            [ColumnSpec("Contenedor", "text"), ColumnSpec("Proveedor", "text"),
             ColumnSpec("Destino", "text"), ColumnSpec("Estado", "status"),
             ColumnSpec("Recibido", "text")], w)
        lay.addWidget(self._hist_table, stretch=1)
        return w

    def _load_history(self) -> None:
        def _iso(inp, default):
            try:
                return inp.date_value().isoformat()
            except Exception:
                return default
        model = self._presenter.qr_history(
            _iso(self._hist_from, "1900-01-01"), _iso(self._hist_to, "2999-12-31"))
        self._hist_table.load_rows(model.rows, row_ids=model.row_ids)

    # lifecycle ---------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()
            self._loaded = True

    def reload(self) -> None:
        try:
            avail = self._presenter.qr_available()
            self._assign_table.load_rows(avail.rows, row_ids=avail.row_ids)
            pending = self._presenter.qr_pending()
            self._receive_table.load_rows(pending.rows, row_ids=pending.row_ids)
        except Exception as exc:
            QMessageBox.warning(self, "Recepción QR", f"No fue posible cargar:\n{exc}")
