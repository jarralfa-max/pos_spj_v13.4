"""Dispositivos page — first section with REAL CRUD wired for
Configuración (SET-25 follow-up): register a device profile, register a
device, edit name/notes, and drive its full lifecycle
(activar/desactivar/bloquear/desbloquear/retirar).

Also carries SET-8's Routing/Failover pillar (`PrintRoute` — which
device a document_type prints to, with an ordered fallback chain) as an
independent "Rutas de impresión" table — unlike Estaciones' Assignments
table, this one isn't selection-driven by the main table (a route isn't
scoped to one selected device), it just lists every route and reloads
whenever the page does.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    BlockDeviceDialog,
    DeviceCreateDialog,
    DeviceEditDialog,
    DeviceProfileCreateDialog,
    PrintRouteCreateDialog,
    PrintRouteEditDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_ROUTE_COLUMNS = [
    ColumnSpec("Tipo de documento"), ColumnSpec("Principal"), ColumnSpec("Respaldo"),
    ColumnSpec("Ámbito"), ColumnSpec("Activa", "status"),
]


class DispositivosPage(ConfiguracionWorkspacePage):
    page_id = "config_dispositivos"
    title = "Dispositivos"
    subtitle = "Impresoras, básculas, cajones y terminales."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Spacing.SM)
        self.new_profile_button = create_secondary_button(actions, "Nuevo perfil")
        self.new_device_button = create_primary_button(actions, "Nuevo dispositivo")
        self.edit_button = create_secondary_button(actions, "Editar")
        self.activate_button = create_secondary_button(actions, "Activar")
        self.deactivate_button = create_warning_button(actions, "Desactivar")
        self.block_button = create_danger_button(actions, "Bloquear")
        self.unblock_button = create_secondary_button(actions, "Desbloquear")
        self.retire_button = create_danger_button(actions, "Retirar")
        for button in (
            self.new_profile_button, self.new_device_button, self.edit_button, self.activate_button,
            self.deactivate_button, self.block_button, self.unblock_button, self.retire_button,
        ):
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        self.layout().insertWidget(1, actions)

        self.new_profile_button.clicked.connect(self._on_new_profile)
        self.new_device_button.clicked.connect(self._on_new_device)
        self.edit_button.clicked.connect(self._on_edit)
        self.activate_button.clicked.connect(lambda: self._on_change_status("ACTIVATE"))
        self.deactivate_button.clicked.connect(lambda: self._on_change_status("DEACTIVATE"))
        self.block_button.clicked.connect(self._on_block)
        self.unblock_button.clicked.connect(lambda: self._on_change_status("UNBLOCK"))
        self.retire_button.clicked.connect(lambda: self._on_change_status("RETIRE"))

        self.routes_card = SectionCard(self, title="Rutas de impresión")
        self.routes_table = StandardTable(_ROUTE_COLUMNS, self.routes_card)
        self.routes_table.setAccessibleName("Rutas de impresión por tipo de documento")
        self.routes_card.add(self.routes_table)
        self.routes_empty = None

        route_actions = QWidget(self.routes_card)
        route_actions_layout = QHBoxLayout(route_actions)
        route_actions_layout.setContentsMargins(0, 0, 0, 0)
        route_actions_layout.setSpacing(Spacing.SM)
        self.new_route_button = create_primary_button(route_actions, "Nueva ruta")
        self.edit_route_button = create_secondary_button(route_actions, "Editar ruta")
        self.activate_route_button = create_secondary_button(route_actions, "Activar ruta")
        self.deactivate_route_button = create_warning_button(route_actions, "Desactivar ruta")
        for button in (
            self.new_route_button, self.edit_route_button, self.activate_route_button,
            self.deactivate_route_button,
        ):
            route_actions_layout.addWidget(button)
        route_actions_layout.addStretch(1)
        self.routes_card.add(route_actions)

        self.layout().addWidget(self.routes_card)

        self.new_route_button.clicked.connect(self._on_new_route)
        self.edit_route_button.clicked.connect(self._on_edit_route)
        self.activate_route_button.clicked.connect(lambda: self._on_change_route_status("ACTIVATE"))
        self.deactivate_route_button.clicked.connect(lambda: self._on_change_route_status("DEACTIVATE"))

        self._routes_by_id: dict = {}
        self._reload_routes()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        self._reload_routes()

    def _selected_device_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Dispositivos", "Selecciona un dispositivo primero.")
        return row_id

    def _reload_routes(self) -> None:
        routes = self._presenter.list_print_routes()
        self._routes_by_id = {r.entity_id: r for r in routes}
        rows = [
            [
                r.document_type, r.primary_device_code,
                ", ".join(r.fallback_device_ids) if r.fallback_device_ids else "—",
                r.branch_id or (r.module or (r.channel or "Global")),
                "Sí" if r.active else "No",
            ]
            for r in routes
        ]
        self.routes_table.load_rows(rows, row_ids=[r.entity_id for r in routes])
        if self.routes_empty is not None:
            self.routes_empty.setParent(None)
            self.routes_empty = None
        if not rows:
            self.routes_empty = create_state_widget(
                ViewState.EMPTY, self.routes_card, message="No hay rutas de impresión configuradas.",
            )
            self.routes_card.add(self.routes_empty)
        self.routes_table.setVisible(bool(rows))

    def _selected_route_id(self) -> str | None:
        row_id = self.routes_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Dispositivos", "Selecciona una ruta primero.")
        return row_id

    def _on_new_profile(self) -> None:
        dlg = DeviceProfileCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"] or not values["device_type"] or not values["connection_type"]:
            QMessageBox.warning(self, "Dispositivos", "Nombre, tipo y conexión son obligatorios.")
            return
        ok, message = self._presenter.register_device_profile(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)

    def _on_new_device(self) -> None:
        branches = self._presenter.list_branches()
        profiles = self._presenter.list_device_profiles()
        if not profiles:
            QMessageBox.warning(
                self, "Dispositivos",
                "No hay perfiles de dispositivo activos todavía. Crea un perfil primero con "
                "«Nuevo perfil».",
            )
            return
        dlg = DeviceCreateDialog(self, branch_options=branches, profile_options=profiles)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["branch_id"] or not values["profile_id"] or not values["code"] or not values["name"]:
            QMessageBox.warning(self, "Dispositivos", "Sucursal, perfil, código y nombre son obligatorios.")
            return
        ok, message = self._presenter.register_device(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit(self) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            return
        device = self._presenter.get_device(device_id)
        if device is None:
            QMessageBox.warning(self, "Dispositivos", "El dispositivo ya no existe.")
            return
        dlg = DeviceEditDialog(self, name=device.name, notes=device.notes)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        ok, message = self._presenter.update_device(device_id=device_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self.reload(self.search.text())

    def _on_block(self) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            return
        dlg = BlockDeviceDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.change_device_status(
            device_id=device_id, action="BLOCK", reason=dlg.reason_text(),
        )
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_status(self, action: str) -> None:
        device_id = self._selected_device_id()
        if not device_id:
            return
        ok, message = self._presenter.change_device_status(device_id=device_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self.reload(self.search.text())

    def _on_new_route(self) -> None:
        devices = self._presenter.list_devices()
        if not devices:
            QMessageBox.warning(self, "Dispositivos", "No hay dispositivos activos todavía.")
            return
        branches = self._presenter.list_branches()
        dlg = PrintRouteCreateDialog(self, device_options=devices, branch_options=branches)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["document_type"] or not values["primary_device_id"]:
            QMessageBox.warning(self, "Dispositivos", "Tipo de documento y dispositivo principal son obligatorios.")
            return
        ok, message = self._presenter.create_print_route(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self._reload_routes()

    def _on_edit_route(self) -> None:
        route_id = self._selected_route_id()
        if not route_id:
            return
        route = self._routes_by_id.get(route_id)
        devices = self._presenter.list_devices()
        fallback_codes = ", ".join(
            next((d.code for d in devices if d.entity_id == fid), fid) for fid in route.fallback_device_ids
        ) if route else ""
        dlg = PrintRouteEditDialog(
            self, device_options=devices, primary_device_code=route.primary_device_code if route else "",
            fallback_codes=fallback_codes,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["primary_device_id"]:
            QMessageBox.warning(self, "Dispositivos", "Selecciona un dispositivo principal.")
            return
        ok, message = self._presenter.update_print_route(route_id=route_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self._reload_routes()

    def _on_change_route_status(self, action: str) -> None:
        route_id = self._selected_route_id()
        if not route_id:
            return
        ok, message = self._presenter.change_print_route_status(route_id=route_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Dispositivos", message)
        if ok:
            self._reload_routes()


__all__ = ["DispositivosPage"]
