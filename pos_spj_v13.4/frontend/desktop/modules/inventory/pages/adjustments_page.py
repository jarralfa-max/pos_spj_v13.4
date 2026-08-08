"""Adjustments page (INV-25 / §14 / P0-C) — crear, aprobar, postear y reversar
ajustes de inventario.

Lista los ajustes recientes de la sucursal (folio, motivo, almacén, estado,
creado) y permite actuar sobre la fila seleccionada: crear un ajuste nuevo,
aprobarlo (si quedó pendiente de aprobación), postearlo (aplica el movimiento
de inventario) o reversarlo (si ya está posteado — irreversible). Todos los
valores y mutaciones pasan por el presenter, que llama a los use cases
autorizados reales; esta página no tiene SQL ni lógica de negocio — sólo
confirma intención y muestra el resultado.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    StandardTable,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import ConfirmationDialog
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.inventory.dialogs import (
    CreateAdjustmentDialog,
    ReverseAdjustmentDialog,
)
from frontend.desktop.themes.tokens import Spacing


class AdjustmentsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryAdjustmentsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Ajustes",
            subtitle="Ajustes con motivo, autorización y posteo.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nuevo ajuste")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.approve_button = create_secondary_button(text="Aprobar")
        self.approve_button.clicked.connect(self._on_approve)
        actions.addWidget(self.approve_button)
        self.post_button = create_secondary_button(text="Postear")
        self.post_button.clicked.connect(self._on_post)
        actions.addWidget(self.post_button)
        self.reverse_button = create_danger_button(text="Reversar")
        self.reverse_button.clicked.connect(self._on_reverse)
        actions.addWidget(self.reverse_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Motivo", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Creado", "text"),
        ])
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.adjustments()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_adjustment_id(self) -> str | None:
        aid = self._table.selected_row_id()
        if not aid:
            QMessageBox.information(
                self, "Ajustes", "Selecciona un ajuste de la lista.")
            return None
        return aid

    def _on_create(self) -> None:
        dlg = CreateAdjustmentDialog(self, product_provider=self._presenter.product_options)
        if dlg.exec_() != QDialog.Accepted:
            return
        product_id = dlg.product_id()
        if not product_id:
            QMessageBox.warning(self, "Ajustes", "Selecciona un producto de la lista.")
            return
        quantity_delta = dlg.quantity_delta()
        if not quantity_delta:
            QMessageBox.warning(self, "Ajustes", "Captura una cantidad mayor a cero.")
            return
        ok, message, _ = self._presenter.create_adjustment(
            product_id=product_id, reason=dlg.reason_code(),
            quantity_delta=quantity_delta, reason_note=dlg.note())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ajustes", message)
        if ok:
            self.refresh()

    def _on_approve(self) -> None:
        aid = self._selected_adjustment_id()
        if aid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Aprobar ajuste",
            message="El ajuste quedará listo para postear. ¿Continuar?",
            confirm_text="Aprobar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.approve_adjustment(adjustment_id=aid)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ajustes", message)
        if ok:
            self.refresh()

    def _on_post(self) -> None:
        aid = self._selected_adjustment_id()
        if aid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Postear ajuste",
            message="Se aplicará el movimiento de inventario. ¿Continuar?",
            confirm_text="Postear")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.post_adjustment(adjustment_id=aid)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ajustes", message)
        if ok:
            self.refresh()

    def _on_reverse(self) -> None:
        aid = self._selected_adjustment_id()
        if aid is None:
            return
        dlg = ReverseAdjustmentDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.reverse_adjustment(
            adjustment_id=aid, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ajustes", message)
        if ok:
            self.refresh()
