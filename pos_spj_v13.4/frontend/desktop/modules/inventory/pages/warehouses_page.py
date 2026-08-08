"""Warehouses page (INV-5 / P0-C) — crear, activar y bloquear almacenes.

Lista los almacenes de la sucursal (código, nombre, tipo, estado) y permite
dar de alta uno nuevo o cambiar el estado del seleccionado. Antes de esta
slice la página era de sólo lectura — sin botón de alta, el hallazgo que la
auditoría funcional señaló explícitamente (§7.4). Doble clic sobre una fila
es un atajo al mismo cambio de estado que el botón correspondiente (activar
si está bloqueado, bloquear si está activo), siempre con confirmación. Todos
los valores y mutaciones pasan por el presenter, que llama a los use cases
autorizados reales; esta página no tiene SQL ni lógica de negocio.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
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
    BlockReasonDialog,
    CreateWarehouseDialog,
)
from frontend.desktop.themes.tokens import Spacing

_STATUS_COLUMN = 3
_ACTIVE_LABEL = "Activo"


class WarehousesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("warehousesPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Almacenes",
            subtitle="Almacenes de la sucursal: tipo, estado y capacidades.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nuevo almacén")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.activate_button = create_secondary_button(text="Activar")
        self.activate_button.clicked.connect(self._on_activate)
        actions.addWidget(self.activate_button)
        self.block_button = create_danger_button(text="Bloquear")
        self.block_button.clicked.connect(self._on_block)
        actions.addWidget(self.block_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Código", "text"),
            ColumnSpec("Nombre", "text"),
            ColumnSpec("Tipo", "text"),
            ColumnSpec("Estado", "status"),
        ])
        self._table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

    def refresh(self) -> None:
        table = self._presenter.warehouses()
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _selected_warehouse_id(self) -> str | None:
        wid = self._table.selected_row_id()
        if not wid:
            QMessageBox.information(
                self, "Almacenes", "Selecciona un almacén de la lista.")
            return None
        return wid

    def _is_active(self, row: int) -> bool:
        item = self._table.item(row, _STATUS_COLUMN)
        return bool(item) and item.text() == _ACTIVE_LABEL

    def _on_create(self) -> None:
        dlg = CreateWarehouseDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        code, name = dlg.code(), dlg.name()
        if not code or not name:
            QMessageBox.warning(self, "Almacenes", "Captura código y nombre.")
            return
        self.create_button.setEnabled(False)
        try:
            ok, message, _ = self._presenter.create_warehouse(
                code=code, name=name, warehouse_type=dlg.warehouse_type())
        finally:
            self.create_button.setEnabled(True)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Almacenes", message)
        if ok:
            self.refresh()

    def _on_activate(self) -> None:
        wid = self._selected_warehouse_id()
        if wid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Activar almacén",
            message="El almacén volverá a estar disponible. ¿Continuar?",
            confirm_text="Activar")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(wid, activate=True, reason="")

    def _on_block(self) -> None:
        wid = self._selected_warehouse_id()
        if wid is None:
            return
        dlg = BlockReasonDialog(self, title="Bloquear almacén")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(wid, activate=False, reason=dlg.reason())

    def _run_status_change(self, warehouse_id: str, *, activate: bool, reason: str) -> None:
        self.activate_button.setEnabled(False)
        self.block_button.setEnabled(False)
        try:
            ok, message, _ = self._presenter.set_warehouse_status(
                warehouse_id=warehouse_id, activate=activate, reason=reason)
        finally:
            self.activate_button.setEnabled(True)
            self.block_button.setEnabled(True)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Almacenes", message)
        if ok:
            self.refresh()

    def _on_double_click(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        wid = item.data(Qt.UserRole) if item is not None else None
        if not wid:
            return
        active = self._is_active(row)
        dlg = ConfirmationDialog(
            self, title="Bloquear almacén" if active else "Activar almacén",
            message=("El almacén dejará de estar disponible. ¿Continuar?" if active
                     else "El almacén volverá a estar disponible. ¿Continuar?"),
            confirm_text="Bloquear" if active else "Activar")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(wid, activate=not active, reason="")
