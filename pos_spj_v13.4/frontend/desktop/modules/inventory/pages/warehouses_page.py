"""Warehouses page (INV-5 / P0-C) — crear, editar, activar, bloquear,
desactivar almacenes y gestionar sus zonas.

Lista los almacenes de la sucursal (código, nombre, tipo, estado) y permite
dar de alta uno nuevo, editarlo, cambiar su estado o abrir sus zonas. Doble
clic sobre una fila es un atajo al mismo cambio de estado que el botón
correspondiente (activar si está bloqueado, bloquear si está activo), siempre
con confirmación. Cada acción se muestra u oculta según las capabilities de la
sesión (§17) — el backend revalida cada una igual, ocultar es sólo UX. Todos
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
    EditWarehouseDialog,
    ManageZonesDialog,
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
        self.edit_button = create_secondary_button(text="Editar")
        self.edit_button.clicked.connect(self._on_edit)
        actions.addWidget(self.edit_button)
        self.zones_button = create_secondary_button(text="Zonas")
        self.zones_button.clicked.connect(self._on_zones)
        actions.addWidget(self.zones_button)
        self.activate_button = create_secondary_button(text="Activar")
        self.activate_button.clicked.connect(self._on_activate)
        actions.addWidget(self.activate_button)
        self.block_button = create_danger_button(text="Bloquear")
        self.block_button.clicked.connect(self._on_block)
        actions.addWidget(self.block_button)
        self.deactivate_button = create_danger_button(text="Desactivar")
        self.deactivate_button.clicked.connect(self._on_deactivate)
        actions.addWidget(self.deactivate_button)
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
        caps = self._presenter.capabilities()
        self.create_button.setVisible(caps.warehouse_create)
        self.edit_button.setVisible(caps.warehouse_edit)
        self.zones_button.setVisible(caps.location_manage)
        self.activate_button.setVisible(caps.warehouse_activate)
        self.block_button.setVisible(caps.warehouse_block)
        self.deactivate_button.setVisible(caps.warehouse_deactivate)

    def _selected_warehouse_id(self) -> str | None:
        wid = self._table.selected_row_id()
        if not wid:
            QMessageBox.information(
                self, "Almacenes", "Selecciona un almacén de la lista.")
            return None
        return wid

    def _selected_warehouse_label(self) -> str:
        row = self._table.currentRow()
        if row < 0:
            return ""
        code = self._table.item(row, 0)
        name = self._table.item(row, 1)
        code_v = code.text() if code is not None else ""
        name_v = name.text() if name is not None else ""
        return f"{code_v} — {name_v}".strip(" —")

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
                code=code, name=name, warehouse_type=dlg.warehouse_type(),
                temperature_profile=dlg.temperature_profile(), capacity=dlg.capacity(),
                capacity_uom=dlg.capacity_uom())
        finally:
            self.create_button.setEnabled(True)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Almacenes", message)
        if ok:
            self.refresh()

    def _on_edit(self) -> None:
        wid = self._selected_warehouse_id()
        if wid is None:
            return
        row = self._presenter.warehouse_detail(warehouse_id=wid)
        if row is None:
            QMessageBox.warning(self, "Almacenes", "Almacén no encontrado.")
            return
        dlg = EditWarehouseDialog(self, warehouse=row)
        if dlg.exec_() != QDialog.Accepted:
            return
        name = dlg.name()
        if not name:
            QMessageBox.warning(self, "Almacenes", "Captura un nombre.")
            return
        ok, message, _ = self._presenter.update_warehouse(
            warehouse_id=wid, name=name, warehouse_type=dlg.warehouse_type(),
            temperature_profile=dlg.temperature_profile(), capacity=dlg.capacity(),
            capacity_uom=dlg.capacity_uom())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Almacenes", message)
        if ok:
            self.refresh()

    def _on_zones(self) -> None:
        wid = self._selected_warehouse_id()
        if wid is None:
            return
        label = self._selected_warehouse_label()

        def create_zone(*, code: str, name: str, zone_type: str) -> None:
            ok, message, _ = self._presenter.create_zone(
                warehouse_id=wid, code=code, name=name, zone_type=zone_type)
            if ok:
                dlg.set_rows(self._presenter.zones(warehouse_id=wid))
            else:
                QMessageBox.warning(self, "Zonas", message)

        dlg = ManageZonesDialog(
            self, warehouse_label=label, table=self._presenter.zones(warehouse_id=wid),
            create_zone=create_zone)
        dlg.exec_()

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
        dlg = BlockReasonDialog(self, title="Bloquear almacén", ok_text="Bloquear")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(wid, activate=False, reason=dlg.reason())

    def _on_deactivate(self) -> None:
        wid = self._selected_warehouse_id()
        if wid is None:
            return
        dlg = BlockReasonDialog(self, title="Desactivar almacén", ok_text="Desactivar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.deactivate_warehouse(
            warehouse_id=wid, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Almacenes", message)
        if ok:
            self.refresh()

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
