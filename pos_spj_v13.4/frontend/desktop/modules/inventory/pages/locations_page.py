"""Locations page (INV-5 / P0-C) — jerarquía de ubicaciones de un almacén.

Selector de almacén (``SearchableComboBox`` — DS, §24) para que la página sea
utilizable por sí sola desde la navegación lateral; sin él el árbol quedaba
siempre vacío en uso real.

Acciones: "Nueva ubicación" crea una raíz en el almacén elegido; el menú
contextual sobre una fila ofrece "Agregar sub-ubicación" (jerarquía real,
pasillo → rack → nivel → posición) además de editar/activar/bloquear/
desactivar; doble clic alterna el estado con confirmación, igual que en
Almacenes. Cada acción se muestra según las capabilities de la sesión (§17).
Todo pasa por el presenter — sin SQL ni lógica de negocio aquí.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

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
from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.modules.inventory.dialogs import (
    BlockReasonDialog,
    CreateLocationDialog,
    EditLocationDialog,
)
from frontend.desktop.themes.tokens import Spacing

_STATUS_COLUMN = 3
_ACTIVE_LABEL = "Activa"


class LocationsPage(QWidget):
    def __init__(self, presenter, warehouse_id=None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("locationsPage")
        self._presenter = presenter
        self._warehouse_id = warehouse_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Ubicaciones",
            subtitle="Jerarquía de ubicaciones: pasillo → rack → nivel → posición.",
            icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        actions = QHBoxLayout()
        self.warehouse_combo = SearchableComboBox(self, placeholder="Selecciona un almacén…")
        self.warehouse_combo.setMinimumWidth(220)
        self.warehouse_combo.selection_changed.connect(self._on_warehouse_changed)
        actions.addWidget(self.warehouse_combo)
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nueva ubicación")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        self.edit_button = create_secondary_button(text="Editar")
        self.edit_button.clicked.connect(self._on_edit)
        actions.addWidget(self.edit_button)
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
            ColumnSpec("Nivel", "numeric"),
            ColumnSpec("Estado", "status"),
        ])
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._table)

        self._load_warehouse_options()

    def _load_warehouse_options(self) -> None:
        options = [(o.id, o.label) for o in self._presenter.warehouse_options()]
        self.warehouse_combo.set_options(options, keep_selection=True)
        if self._warehouse_id:
            self.warehouse_combo.set_current_id(self._warehouse_id)
        elif options:
            self._warehouse_id = options[0][0]
            self.warehouse_combo.set_current_id(self._warehouse_id)

    def set_warehouse(self, warehouse_id: str) -> None:
        self._warehouse_id = warehouse_id
        self.warehouse_combo.set_current_id(warehouse_id)
        self.refresh()

    def _on_warehouse_changed(self, warehouse_id) -> None:
        self._warehouse_id = warehouse_id
        self.refresh()

    def refresh(self) -> None:
        if not self._warehouse_id:
            self._table.load_rows([])
        else:
            table = self._presenter.location_tree(warehouse_id=self._warehouse_id)
            self._table.load_rows(table.rows, row_ids=table.row_ids)
        caps = self._presenter.capabilities()
        self.create_button.setVisible(caps.location_manage)
        self.edit_button.setVisible(caps.location_manage)
        self.activate_button.setVisible(caps.location_manage)
        self.block_button.setVisible(caps.location_manage)
        self.deactivate_button.setVisible(caps.location_manage)

    def _selected_location_id(self) -> str | None:
        lid = self._table.selected_row_id()
        if not lid:
            QMessageBox.information(
                self, "Ubicaciones", "Selecciona una ubicación de la lista.")
            return None
        return lid

    def _is_active(self, row: int) -> bool:
        item = self._table.item(row, _STATUS_COLUMN)
        return bool(item) and item.text() == _ACTIVE_LABEL

    def _on_create(self, *, parent_location_id: str | None = None,
                   parent_label: str | None = None) -> None:
        if not self._warehouse_id:
            QMessageBox.information(self, "Ubicaciones", "Selecciona un almacén primero.")
            return
        dlg = CreateLocationDialog(self, parent_label=parent_label)
        if dlg.exec_() != QDialog.Accepted:
            return
        code, name = dlg.code(), dlg.name()
        if not code or not name:
            QMessageBox.warning(self, "Ubicaciones", "Captura código y nombre.")
            return
        self.create_button.setEnabled(False)
        try:
            ok, message, _ = self._presenter.create_location(
                warehouse_id=self._warehouse_id, code=code, name=name,
                level=dlg.level(), parent_location_id=parent_location_id,
                capacity=dlg.capacity())
        finally:
            self.create_button.setEnabled(True)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ubicaciones", message)
        if ok:
            self.refresh()

    def _on_edit(self) -> None:
        lid = self._selected_location_id()
        if lid is None:
            return
        row = self._presenter.location_detail(location_id=lid)
        if row is None:
            QMessageBox.warning(self, "Ubicaciones", "Ubicación no encontrada.")
            return
        dlg = EditLocationDialog(self, location=row)
        if dlg.exec_() != QDialog.Accepted:
            return
        name = dlg.name()
        if not name:
            QMessageBox.warning(self, "Ubicaciones", "Captura un nombre.")
            return
        ok, message, _ = self._presenter.update_location(
            location_id=lid, name=name, capacity=dlg.capacity())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ubicaciones", message)
        if ok:
            self.refresh()

    def _on_activate(self) -> None:
        lid = self._selected_location_id()
        if lid is None:
            return
        dlg = ConfirmationDialog(
            self, title="Activar ubicación",
            message="La ubicación volverá a estar disponible. ¿Continuar?",
            confirm_text="Activar")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(lid, activate=True, reason="")

    def _on_block(self) -> None:
        lid = self._selected_location_id()
        if lid is None:
            return
        dlg = BlockReasonDialog(self, title="Bloquear ubicación", ok_text="Bloquear")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(lid, activate=False, reason=dlg.reason())

    def _on_deactivate(self) -> None:
        lid = self._selected_location_id()
        if lid is None:
            return
        dlg = BlockReasonDialog(self, title="Desactivar ubicación", ok_text="Desactivar")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message, _ = self._presenter.deactivate_location(
            location_id=lid, reason=dlg.reason())
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ubicaciones", message)
        if ok:
            self.refresh()

    def _run_status_change(self, location_id: str, *, activate: bool, reason: str) -> None:
        self.activate_button.setEnabled(False)
        self.block_button.setEnabled(False)
        try:
            ok, message, _ = self._presenter.set_location_status(
                location_id=location_id, activate=activate, reason=reason)
        finally:
            self.activate_button.setEnabled(True)
            self.block_button.setEnabled(True)
        (QMessageBox.information if ok else QMessageBox.warning)(
            self, "Ubicaciones", message)
        if ok:
            self.refresh()

    def _on_double_click(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        lid = item.data(Qt.UserRole) if item is not None else None
        if not lid:
            return
        active = self._is_active(row)
        dlg = ConfirmationDialog(
            self, title="Bloquear ubicación" if active else "Activar ubicación",
            message=("La ubicación dejará de estar disponible. ¿Continuar?" if active
                     else "La ubicación volverá a estar disponible. ¿Continuar?"),
            confirm_text="Bloquear" if active else "Activar")
        if dlg.exec_() != QDialog.Accepted:
            return
        self._run_status_change(lid, activate=not active, reason="")

    def _on_context_menu(self, position) -> None:
        row = self._table.rowAt(position.y())
        if row < 0:
            return
        self._table.selectRow(row)
        item = self._table.item(row, 0)
        lid = item.data(Qt.UserRole) if item is not None else None
        if not lid:
            return
        label = item.text().strip("· ")
        active = self._is_active(row)
        menu = QMenu(self)
        add_sub = menu.addAction("Agregar sub-ubicación")
        edit_action = menu.addAction("Editar")
        menu.addSeparator()
        toggle = menu.addAction("Bloquear" if active else "Activar")
        deactivate_action = menu.addAction("Desactivar")
        chosen = menu.exec_(self._table.viewport().mapToGlobal(position))
        if chosen is add_sub:
            self._on_create(parent_location_id=lid, parent_label=label)
        elif chosen is edit_action:
            self._on_edit()
        elif chosen is toggle:
            if active:
                self._on_block()
            else:
                self._on_activate()
        elif chosen is deactivate_action:
            self._on_deactivate()
