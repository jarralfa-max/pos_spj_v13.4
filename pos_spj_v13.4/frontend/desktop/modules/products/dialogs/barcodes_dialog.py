"""BarcodesDialog — códigos de barras y códigos alternos de UN producto (§17, PROD-22).

UI only: lista lo asignado y permite asignar un código (EAN/UPC/GTIN validan
dígito verificador en el dominio; un código activo pertenece a un solo
producto), activarlo/desactivarlo y agregar códigos alternos (de proveedor).
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
)

from frontend.desktop.components import ColumnSpec, StandardTable
from frontend.desktop.components.barcode_input import BarcodeInput
from frontend.desktop.components.buttons import (
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.modules.products.product_codes_profiles_presenter import (
    BARCODE_TYPE_ES,
)
from frontend.desktop.themes.tokens import DialogMetrics


class BarcodesDialog(StandardDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent, title=f"Códigos de «{product_name}»",
                         width=DialogMetrics.WIDTH_LG)
        self.setObjectName("productBarcodesDialog")
        self.setMinimumSize(720, 520)
        self._p = presenter
        self._product_id = product_id
        self._barcodes: list[dict] = []
        layout = self.content_layout()

        assign = SectionCard(self, title="Asignar código de barras")
        form = QFormLayout()
        self.value = BarcodeInput(clear_after_scan=False)
        self.value.setAccessibleName("Código de barras")
        self.barcode_type = QComboBox()
        for key, label in BARCODE_TYPE_ES.items():
            self.barcode_type.addItem(label, key)
        self.primary = QCheckBox("Principal (el que lee el POS)")
        form.addRow("Código *", self.value)
        form.addRow("Tipo *", self.barcode_type)
        form.addRow("", self.primary)
        assign.body().addLayout(form)
        self.btn_assign = create_primary_button(self, "Asignar")
        self.btn_assign.clicked.connect(self._assign)
        assign_row = QHBoxLayout()
        assign_row.addStretch(1)
        assign_row.addWidget(self.btn_assign)
        assign.body().addLayout(assign_row)
        layout.addWidget(assign)

        self.barcodes_table = StandardTable(columns=[
            ColumnSpec("Código", "text"), ColumnSpec("Tipo", "text"),
            ColumnSpec("Principal", "status"), ColumnSpec("Estado", "status")])
        self.barcodes_table.setMinimumHeight(170)
        layout.addWidget(self.barcodes_table, 1)
        row = QHBoxLayout()
        self.btn_toggle = create_secondary_button(self, "Activar/Desactivar")
        self.btn_toggle.clicked.connect(self._toggle)
        row.addWidget(self.btn_toggle)
        row.addStretch(1)
        layout.addLayout(row)

        alternate = SectionCard(self, title="Códigos alternos (proveedor)")
        alt_row = QHBoxLayout()
        self.alternate = StandardLineEdit(placeholder="Código con el que lo vende el proveedor")
        self.btn_alternate = create_secondary_button(self, "Agregar")
        self.btn_alternate.clicked.connect(self._add_alternate)
        alt_row.addWidget(self.alternate, 1)
        alt_row.addWidget(self.btn_alternate)
        alternate.body().addLayout(alt_row)
        self.alternate_table = StandardTable(columns=[
            ColumnSpec("Código", "text"), ColumnSpec("Estado", "status")])
        alternate.add(self.alternate_table)
        layout.addWidget(alternate)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setProperty("role", "banner")
        self.message.hide()
        layout.addWidget(self.message)

        close = QDialogButtonBox(QDialogButtonBox.Close, self)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        layout.addWidget(close)

        can_barcodes = bool(getattr(self._p, "can_manage_barcodes", False))
        for widget in (self.value, self.barcode_type, self.primary, self.btn_assign,
                       self.btn_toggle):
            widget.setEnabled(can_barcodes)
        can_alt = bool(getattr(self._p, "can_manage_alternate_codes", False))
        self.alternate.setEnabled(can_alt)
        self.btn_alternate.setEnabled(can_alt)
        self.refresh()

    def refresh(self) -> None:
        self._barcodes = self._p.barcodes(self._product_id)
        self.barcodes_table.load_rows(
            [[b["value"], BARCODE_TYPE_ES.get(b["barcode_type"], b["barcode_type"]),
              "Principal" if b["is_primary"] else "",
              "Activo" if b["active"] else "Inactivo"] for b in self._barcodes],
            row_ids=[b["id"] for b in self._barcodes])
        alternates = self._p.alternate_codes(self._product_id)
        self.alternate_table.load_rows(
            [[a["code"], "Activo" if a["active"] else "Inactivo"] for a in alternates],
            row_ids=[a["id"] for a in alternates])

    def _show(self, ok: bool, text: str) -> None:
        self.message.setText(text)
        self.message.setProperty("state", "success" if ok else "error")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(bool(text))

    def _assign(self) -> None:
        value = self.value.text().strip()
        if not value:
            self._show(False, "Escribe o escanea el código.")
            return
        ok, message = self._p.assign_barcode(
            product_id=self._product_id, value=value,
            barcode_type=self.barcode_type.currentData(),
            is_primary=self.primary.isChecked())
        self._show(ok, "Código asignado." if ok else message)
        if ok:
            self.value.clear()
            self.primary.setChecked(False)
            self.refresh()

    def _toggle(self) -> None:
        barcode_id = self.barcodes_table.selected_row_id()
        if not barcode_id:
            QMessageBox.information(self, "Códigos", "Selecciona un código.")
            return
        row = next((b for b in self._barcodes if b["id"] == barcode_id), {})
        ok, message = self._p.set_barcode_active(barcode_id, not row.get("active"))
        self._show(ok, "Código actualizado." if ok else message)
        if ok:
            self.refresh()

    def _add_alternate(self) -> None:
        code = self.alternate.text().strip()
        if not code:
            self._show(False, "Escribe el código alterno.")
            return
        ok, message = self._p.add_alternate_code(product_id=self._product_id, code=code)
        self._show(ok, "Código alterno agregado." if ok else message)
        if ok:
            self.alternate.clear()
            self.refresh()
