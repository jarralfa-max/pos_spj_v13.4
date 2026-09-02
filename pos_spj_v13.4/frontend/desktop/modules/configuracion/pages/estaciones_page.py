"""Estaciones (General) page — SET-6's domain (`Workstation`) had zero
UI before this round, same "domain done, zero CRUD" gap already closed
for Dispositivos/Documentos/Empresa. Mirrors `dispositivos_page.py`'s
shape — register, edit name/identifier/OS, and drive the full lifecycle
(activar/desactivar/mantenimiento/bloquear/desbloquear/retirar).

Also carries SET-7's fourth pillar (Assignments — which device plays
which role at this workstation), closed here rather than on the
Dispositivos page because an assignment is inherently workstation-
centric: selecting a workstation row reloads its assignments into the
secondary table, same selection-driven pattern as `documentos_page.py`'s
Versiones table.

Keeps the class name `GeneralPage` and `page_id = "config_general"` from
the generic placeholder this replaces — the sidebar entry ("General")
and route id are unchanged, only the page gains real actions.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    AssignDeviceDialog,
    BlockWorkstationDialog,
    WorkstationCreateDialog,
    WorkstationEditDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_ASSIGNMENT_COLUMNS = [ColumnSpec("Rol"), ColumnSpec("Dispositivo")]


class GeneralPage(ConfiguracionWorkspacePage):
    page_id = "config_general"
    title = "General"
    subtitle = "Estaciones de trabajo registradas."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Spacing.SM)
        self.new_button = create_primary_button(actions, "Nueva estación")
        self.edit_button = create_secondary_button(actions, "Editar")
        self.activate_button = create_secondary_button(actions, "Activar")
        self.deactivate_button = create_warning_button(actions, "Desactivar")
        self.maintenance_button = create_warning_button(actions, "Mantenimiento")
        self.exit_maintenance_button = create_secondary_button(actions, "Salir de mantenimiento")
        self.block_button = create_danger_button(actions, "Bloquear")
        self.unblock_button = create_secondary_button(actions, "Desbloquear")
        self.retire_button = create_danger_button(actions, "Retirar")
        for button in (
            self.new_button, self.edit_button, self.activate_button, self.deactivate_button,
            self.maintenance_button, self.exit_maintenance_button, self.block_button,
            self.unblock_button, self.retire_button,
        ):
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        self.layout().insertWidget(1, actions)

        self.new_button.clicked.connect(self._on_new)
        self.edit_button.clicked.connect(self._on_edit)
        self.activate_button.clicked.connect(lambda: self._on_change_status("ACTIVATE"))
        self.deactivate_button.clicked.connect(lambda: self._on_change_status("DEACTIVATE"))
        self.maintenance_button.clicked.connect(lambda: self._on_change_status("ENTER_MAINTENANCE"))
        self.exit_maintenance_button.clicked.connect(lambda: self._on_change_status("EXIT_MAINTENANCE"))
        self.block_button.clicked.connect(self._on_block)
        self.unblock_button.clicked.connect(lambda: self._on_change_status("UNBLOCK"))
        self.retire_button.clicked.connect(lambda: self._on_change_status("RETIRE"))

        self.assignments_card = SectionCard(self, title="Dispositivos asignados")
        self.assignments_table = StandardTable(_ASSIGNMENT_COLUMNS, self.assignments_card)
        self.assignments_table.setAccessibleName("Dispositivos asignados a la estación seleccionada")
        self.assignments_card.add(self.assignments_table)
        self.assignments_empty = None

        assignment_actions = QWidget(self.assignments_card)
        assignment_actions_layout = QHBoxLayout(assignment_actions)
        assignment_actions_layout.setContentsMargins(0, 0, 0, 0)
        assignment_actions_layout.setSpacing(Spacing.SM)
        self.assign_button = create_primary_button(assignment_actions, "Asignar dispositivo")
        self.unassign_button = create_danger_button(assignment_actions, "Desasignar")
        assignment_actions_layout.addWidget(self.assign_button)
        assignment_actions_layout.addWidget(self.unassign_button)
        assignment_actions_layout.addStretch(1)
        self.assignments_card.add(assignment_actions)

        self.layout().addWidget(self.assignments_card)

        self.assign_button.clicked.connect(self._on_assign)
        self.unassign_button.clicked.connect(self._on_unassign)

        self._reload_assignments()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        if self.table is not None:
            self.table.itemSelectionChanged.connect(self._reload_assignments)
        self._reload_assignments()

    def _selected_workstation_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Estaciones", "Selecciona una estación primero.")
        return row_id

    def _reload_assignments(self) -> None:
        workstation_id = self.table.selected_row_id() if self.table is not None else None
        assignments = (
            self._presenter.list_workstation_assignments(workstation_id) if workstation_id else ()
        )
        rows = [[a.role, f"{a.device_name} ({a.device_code})"] for a in assignments]
        self.assignments_table.load_rows(rows, row_ids=[a.entity_id for a in assignments])
        if self.assignments_empty is not None:
            self.assignments_empty.setParent(None)
            self.assignments_empty = None
        if not rows:
            message = (
                "Selecciona una estación para ver sus dispositivos asignados." if not workstation_id
                else "Esta estación no tiene dispositivos asignados."
            )
            self.assignments_empty = create_state_widget(
                ViewState.EMPTY, self.assignments_card, message=message,
            )
            self.assignments_card.add(self.assignments_empty)
        self.assignments_table.setVisible(bool(rows))

    def _on_new(self) -> None:
        branches = self._presenter.list_branches()
        dlg = WorkstationCreateDialog(self, branch_options=branches)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["branch_id"] or not values["workstation_type"] or not values["code"] or not values["name"]:
            QMessageBox.warning(self, "Estaciones", "Sucursal, tipo, código y nombre son obligatorios.")
            return
        ok, message = self._presenter.register_workstation(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Estaciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit(self) -> None:
        workstation_id = self._selected_workstation_id()
        if not workstation_id:
            return
        workstation = self._presenter.get_workstation(workstation_id)
        if workstation is None:
            QMessageBox.warning(self, "Estaciones", "La estación ya no existe.")
            return
        dlg = WorkstationEditDialog(
            self, name=workstation.name, device_identifier=workstation.device_identifier,
            operating_system=workstation.operating_system,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        ok, message = self._presenter.update_workstation(workstation_id=workstation_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Estaciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_block(self) -> None:
        workstation_id = self._selected_workstation_id()
        if not workstation_id:
            return
        dlg = BlockWorkstationDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.change_workstation_status(
            workstation_id=workstation_id, action="BLOCK", reason=dlg.reason_text(),
        )
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Estaciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_status(self, action: str) -> None:
        workstation_id = self._selected_workstation_id()
        if not workstation_id:
            return
        ok, message = self._presenter.change_workstation_status(workstation_id=workstation_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Estaciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_assign(self) -> None:
        workstation_id = self._selected_workstation_id()
        if not workstation_id:
            return
        devices = self._presenter.list_devices()
        if not devices:
            QMessageBox.warning(self, "Estaciones", "No hay dispositivos activos todavía.")
            return
        dlg = AssignDeviceDialog(self, device_options=devices)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["role"] or not values["device_id"]:
            QMessageBox.warning(self, "Estaciones", "Rol y dispositivo son obligatorios.")
            return
        ok, message = self._presenter.assign_device(workstation_id=workstation_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Estaciones", message)
        if ok:
            self._reload_assignments()

    def _on_unassign(self) -> None:
        assignment_id = self.assignments_table.selected_row_id()
        if not assignment_id:
            QMessageBox.warning(self, "Estaciones", "Selecciona una asignación primero.")
            return
        ok, message = self._presenter.unassign_device(assignment_id=assignment_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Estaciones", message)
        if ok:
            self._reload_assignments()


__all__ = ["GeneralPage"]
