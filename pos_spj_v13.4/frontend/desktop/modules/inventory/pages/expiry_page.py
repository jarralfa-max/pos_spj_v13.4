"""Expiry page (INV-7 / §9.4 / §27) — lots at risk of expiration + actions.

Lists available lots classified as expired / critical / near expiry (nearest
first), with product, lot, quantity, days-to-expiry and risk. "Generar
alertas" classifies every available lot and enqueues the corresponding
alerts (never moves stock); "Procesar vencidos" moves expired lots' stock to
the EXPIRED bucket. Selecting a row lets you block the lot, send it to
quarantine, or open its full detail (same dialog as Lotes) — each action
gated by the session's capabilities (§17). All values come from the
presenter; no SQL, no business logic here.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_danger_button,
    create_secondary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import EditLotDialog, LotDetailDialog
from frontend.desktop.themes.tokens import Spacing


class ExpiryPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryExpiryPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Caducidades",
            subtitle="Lotes en riesgo de caducidad: vencidos, críticos y próximos.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.alerts_button = create_secondary_button(text="Generar alertas")
        self.alerts_button.clicked.connect(self._on_generate_alerts)
        actions.addWidget(self.alerts_button)
        self.process_button = create_secondary_button(text="Procesar vencidos")
        self.process_button.clicked.connect(self._on_process_expired)
        actions.addWidget(self.process_button)
        self.block_button = create_danger_button(text="Bloquear lote")
        self.block_button.clicked.connect(lambda: self._on_change_status("BLOCKED"))
        actions.addWidget(self.block_button)
        self.quarantine_button = create_secondary_button(text="Enviar a cuarentena")
        self.quarantine_button.clicked.connect(lambda: self._on_change_status("QUARANTINED"))
        actions.addWidget(self.quarantine_button)
        self.detail_button = create_secondary_button(text="Ver lote")
        self.detail_button.clicked.connect(self._on_detail)
        actions.addWidget(self.detail_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Días", "numeric"),
            ColumnSpec("Riesgo", "status"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.expiring()
        self._table.load_rows(table.rows, row_ids=table.row_ids)
        caps = self._presenter.capabilities()
        self.alerts_button.setVisible(caps.lot_view)
        self.process_button.setVisible(caps.lot_block)
        self.block_button.setVisible(caps.lot_block)
        self.quarantine_button.setVisible(caps.lot_block)
        self.detail_button.setVisible(True)

    def _selected_lot_id(self) -> str | None:
        lid = self._table.selected_row_id()
        if not lid:
            QMessageBox.information(
                self, "Caducidades", "Selecciona un lote de la lista.")
            return None
        return lid

    def _on_generate_alerts(self) -> None:
        ok, message, _ = self._presenter.generate_expiry_alerts()
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Caducidades", message)
        if ok:
            self.refresh()

    def _on_process_expired(self) -> None:
        ok, message, _ = self._presenter.process_expired_lots()
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Caducidades", message)
        if ok:
            self.refresh()

    def _on_change_status(self, target_status: str) -> None:
        lid = self._selected_lot_id()
        if lid is None:
            return
        from frontend.desktop.modules.inventory.dialogs import BlockReasonDialog
        title = "Bloquear lote" if target_status == "BLOCKED" else "Enviar a cuarentena"
        dlg = BlockReasonDialog(self, title=title, ok_text="Aplicar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.set_lot_quality_status(
            lot_id=lid, new_status=target_status, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Caducidades", message)
        if ok:
            self.refresh()

    def _on_detail(self) -> None:
        lid = self._selected_lot_id()
        if lid is None:
            return
        header = self._presenter.lot_detail(lot_id=lid)
        if header is None:
            QMessageBox.warning(self, "Caducidades", "Lote no encontrado.")
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
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, "Caducidades", message)
            if ok:
                dlg.accept()
                self.refresh()

        def change_status(new_status: str, reason: str) -> None:
            ok, message, _ = self._presenter.set_lot_quality_status(
                lot_id=lid, new_status=new_status, reason=reason)
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, "Caducidades", message)
            if ok:
                dlg.accept()
                self.refresh()

        def print_label(is_reprint: bool) -> None:
            ok, message, _ = self._presenter.print_lot_label(
                lot_id=lid, is_reprint=is_reprint)
            (QMessageBox.information if ok else QMessageBox.warning)(
                self, "Caducidades", message)

        dlg = LotDetailDialog(
            self, header=header, stock=self._presenter.lot_stock(lot_id=lid),
            movements=self._presenter.lot_movements(lot_id=lid),
            traceability=self._presenter.traceability(lot_id=lid),
            can_edit=caps.lot_edit,
            can_change_status=(caps.lot_block or caps.lot_release),
            can_print=caps.lot_print, can_reprint=caps.lot_reprint,
            edit=edit, change_status=change_status, print_label=print_label)
        dlg.exec_()
