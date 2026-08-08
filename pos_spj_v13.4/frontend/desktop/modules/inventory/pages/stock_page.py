"""Stock page (INV-25 / §14 / P0-E) — existencia física + inspección de recepción.

Lista los balances físicos (producto, almacén, bucket, cantidad, reservado)
de la sucursal. Cuando una fila está "Por inspección" (una recepción de
compra la retuvo ahí — automáticamente, si el producto requiere inspección
de calidad, o porque la recepción lo marcó explícitamente) puede aprobarse
(vuelve a Disponible) o rechazarse (pasa a Bloqueado por calidad, con
motivo). Antes de esta slice nada en el sistema podía sacar una existencia
de ese bucket — la integración Compras→Inventario dejaba la retención sin
salida. Todo pasa por el presenter; sin SQL ni lógica de negocio aquí.
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
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import BlockReasonDialog
from frontend.desktop.themes.tokens import Spacing

_STATUS_COLUMN = 2
_PENDING_INSPECTION_LABEL = "Por inspección"


class StockPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryStockPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Existencias",
            subtitle="Existencia física por producto, almacén y bucket.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.approve_button = create_secondary_button(text="Aprobar inspección")
        self.approve_button.clicked.connect(self._on_approve_inspection)
        actions.addWidget(self.approve_button)
        self.reject_button = create_danger_button(text="Rechazar inspección")
        self.reject_button.clicked.connect(self._on_reject_inspection)
        actions.addWidget(self.reject_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Cantidad", "numeric"),
            ColumnSpec("Reservado", "numeric"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.stock()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_pending_balance_id(self) -> str | None:
        row = self._table.currentRow()
        if row < 0 or not self._table.selected_row_id():
            QMessageBox.information(
                self, "Existencias", "Selecciona una existencia pendiente de inspección.")
            return None
        status_item = self._table.item(row, _STATUS_COLUMN)
        if status_item is None or status_item.text() != _PENDING_INSPECTION_LABEL:
            QMessageBox.information(
                self, "Existencias",
                "Sólo se puede inspeccionar una fila «Por inspección».")
            return None
        return self._table.selected_row_id()

    def _on_approve_inspection(self) -> None:
        balance_id = self._selected_pending_balance_id()
        if balance_id is None:
            return
        dlg = ConfirmationDialog(
            self, title="Aprobar inspección",
            message="La existencia pasará a disponible. ¿Continuar?",
            confirm_text="Aprobar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.inspect_stock(balance_id=balance_id, passed=True)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Existencias", message)
        if ok:
            self.refresh()

    def _on_reject_inspection(self) -> None:
        balance_id = self._selected_pending_balance_id()
        if balance_id is None:
            return
        dlg = BlockReasonDialog(self, title="Rechazar inspección", ok_text="Rechazar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.inspect_stock(
            balance_id=balance_id, passed=False, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Existencias", message)
        if ok:
            self.refresh()
