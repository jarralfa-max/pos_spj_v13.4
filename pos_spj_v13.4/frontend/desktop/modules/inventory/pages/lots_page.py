"""Lots page (INV-7 / §26) — a product's lots by FEFO, register + detail.

An ``EntitySearchInput`` resolves the product by name, code or barcode
against the canonical catalog (§P0-D — never a hand-typed UUID), and the page
lists its lots — code, origin, quality status and expiration — ordered by
earliest expiry (FEFO). "Nuevo lote" registers one for the selected product;
selecting a row and "Ver detalle" opens the full detail (stock, movements,
traceability) with edit/quality-status/label actions, each gated by the
session's capabilities (§17) — the backend re-validates every one
independently. All values come from the presenter; no SQL, no business logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import (
    CreateLotDialog,
    EditLotDialog,
    LotDetailDialog,
)
from frontend.desktop.themes.tokens import Spacing


class LotsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryLotsPage")
        self._presenter = presenter
        self._product_id = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Lotes",
            subtitle="Lotes por producto: origen, estado de calidad y caducidad (FEFO).",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        self._search = EntitySearchInput(
            self, provider=self._presenter.product_options,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self._search.selected.connect(self._on_product_selected)
        layout.addWidget(self._search)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nuevo lote")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.detail_button = create_secondary_button(text="Ver detalle")
        self.detail_button.clicked.connect(self._on_detail)
        actions.addWidget(self.detail_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Lote", "text"),
            ColumnSpec("Origen", "text"),
            ColumnSpec("Calidad", "status"),
            ColumnSpec("Caducidad", "text"),
        ])
        layout.addWidget(self._table)

    def _on_product_selected(self, product_id) -> None:
        self._product_id = str(product_id or "")
        self.refresh()

    def refresh(self) -> None:
        table = self._presenter.lots(product_id=self._product_id)
        self._table.load_rows(table.rows, row_ids=table.row_ids)
        caps = self._presenter.capabilities()
        self.create_button.setVisible(caps.lot_create)
        self.detail_button.setVisible(True)

    def _selected_lot_id(self) -> str | None:
        lid = self._table.selected_row_id()
        if not lid:
            QMessageBox.information(self, "Lotes", "Selecciona un lote de la lista.")
            return None
        return lid

    def _on_create(self) -> None:
        if not self._product_id:
            QMessageBox.information(self, "Lotes", "Selecciona un producto primero.")
            return
        dlg = CreateLotDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        code = dlg.lot_code()
        if not code:
            QMessageBox.warning(self, "Lotes", "Captura el código de lote.")
            return
        ok, message, _ = self._presenter.register_lot(
            product_id=self._product_id, lot_code=code, origin_type=dlg.origin_type(),
            supplier_lot_code=dlg.supplier_lot_code(),
            production_lot_code=dlg.production_lot_code(),
            origin_document_id=dlg.origin_document_id(),
            production_date=dlg.production_date(), expiration_date=dlg.expiration_date())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Lotes", message)
        if ok:
            self.refresh()

    def _on_detail(self) -> None:
        lid = self._selected_lot_id()
        if lid is None:
            return
        header = self._presenter.lot_detail(lot_id=lid)
        if header is None:
            QMessageBox.warning(self, "Lotes", "Lote no encontrado.")
            return
        caps = self._presenter.capabilities()

        def edit() -> None:
            edit_dlg = EditLotDialog(self, lot=header)
            if edit_dlg.exec_() != QDialog.Accepted:
                return
            ok, message, _ = self._presenter.update_lot(
                lot_id=lid, supplier_lot_code=edit_dlg.supplier_lot_code(),
                production_lot_code=edit_dlg.production_lot_code(),
                origin_document_id=edit_dlg.origin_document_id(),
                expiration_date=edit_dlg.expiration_date() or None)
            (QMessageBox.information if ok else QMessageBox.warning)(self, "Lotes", message)
            if ok:
                dlg.accept()
                self.refresh()

        def change_status(new_status: str, reason: str) -> None:
            ok, message, _ = self._presenter.set_lot_quality_status(
                lot_id=lid, new_status=new_status, reason=reason)
            (QMessageBox.information if ok else QMessageBox.warning)(self, "Lotes", message)
            if ok:
                dlg.accept()
                self.refresh()

        def print_label(is_reprint: bool) -> None:
            ok, message, _ = self._presenter.print_lot_label(
                lot_id=lid, is_reprint=is_reprint)
            (QMessageBox.information if ok else QMessageBox.warning)(self, "Lotes", message)

        dlg = LotDetailDialog(
            self, header=header, stock=self._presenter.lot_stock(lot_id=lid),
            movements=self._presenter.lot_movements(lot_id=lid),
            traceability=self._presenter.traceability(lot_id=lid),
            can_edit=caps.lot_edit,
            can_change_status=(caps.lot_block or caps.lot_release),
            can_print=caps.lot_print, can_reprint=caps.lot_reprint,
            edit=edit, change_status=change_status, print_label=print_label)
        dlg.exec_()
