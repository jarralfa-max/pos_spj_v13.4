"""Integraciones page — SET-19 cutover, real CRUD for the Definitions/
Instances/Credentials/Health/Webhooks pillars. Main table lists
`IntegrationDefinition`s; selecting one loads an "Instancias" card
(with an inline Credenciales area); selecting an instance loads
"Webhooks" and "Salud" cards — same selection-cascades-secondary-tables
shape `documentos_page.py` established for Templates→Versions, just
with 2 secondary cards driven by the same selection instead of 1.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    IntegrationDefinitionCreateDialog,
    IntegrationDefinitionEditDialog,
    IntegrationInstanceCreateDialog,
    IntegrationInstanceEditDialog,
    RecordHealthCheckDialog,
    SetCredentialDialog,
    WebhookEndpointCreateDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_INSTANCE_COLUMNS = [ColumnSpec("Nombre"), ColumnSpec("Configuración"), ColumnSpec("Activo", "status")]
_CREDENTIAL_COLUMNS = [ColumnSpec("Credencial"), ColumnSpec("Estado")]
_WEBHOOK_COLUMNS = [
    ColumnSpec("Código"), ColumnSpec("Ruta"), ColumnSpec("Firma"), ColumnSpec("Activo", "status"),
]
_HEALTH_COLUMNS = [ColumnSpec("Resultado", "status"), ColumnSpec("Mensaje"), ColumnSpec("Fecha")]


def _button_row(parent, *buttons):
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Spacing.SM)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


class IntegracionesPage(ConfiguracionWorkspacePage):
    page_id = "config_integraciones"
    title = "Integraciones"
    subtitle = "Definiciones, instancias, credenciales, salud y webhooks."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._selected_definition_id: str | None = None
        self._selected_instance_id: str | None = None
        self._definitions_by_id: dict = {}
        self._instances_by_id: dict = {}

        self.new_definition_button = create_primary_button(self, "Nueva definición")
        self.edit_definition_button = create_secondary_button(self, "Editar definición")
        self.activate_definition_button = create_secondary_button(self, "Activar definición")
        self.deactivate_definition_button = create_warning_button(self, "Desactivar definición")
        definition_actions = _button_row(
            self, self.new_definition_button, self.edit_definition_button,
            self.activate_definition_button, self.deactivate_definition_button,
        )
        self.layout().insertWidget(1, definition_actions)

        self.new_definition_button.clicked.connect(self._on_new_definition)
        self.edit_definition_button.clicked.connect(self._on_edit_definition)
        self.activate_definition_button.clicked.connect(lambda: self._on_change_definition_status("ACTIVATE"))
        self.deactivate_definition_button.clicked.connect(lambda: self._on_change_definition_status("DEACTIVATE"))

        self._build_instances_card()
        self._build_webhooks_card()
        self._build_health_card()

        self._reload_instances()
        self._reload_webhooks()
        self._reload_health()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        if self.table is not None:
            self.table.itemSelectionChanged.connect(self._on_definition_selected)
        self._definitions_by_id = {d.entity_id: d for d in self._presenter.list_integration_definitions()}
        self._selected_definition_id = None
        self._selected_instance_id = None
        self._reload_instances()
        self._reload_webhooks()
        self._reload_health()

    def _on_definition_selected(self) -> None:
        self._selected_definition_id = self.table.selected_row_id() if self.table is not None else None
        self._selected_instance_id = None
        self._reload_instances()
        self._reload_webhooks()
        self._reload_health()

    # ── Instancias + Credenciales ────────────────────────────────────────

    def _build_instances_card(self) -> None:
        self.instances_card = SectionCard(self, title="Instancias")
        self.instances_table = StandardTable(_INSTANCE_COLUMNS, self.instances_card)
        self.instances_table.setAccessibleName("Instancias de la definición seleccionada")
        self.instances_card.add(self.instances_table)
        self.instances_empty = None

        self.new_instance_button = create_primary_button(self.instances_card, "Nueva instancia")
        self.edit_instance_button = create_secondary_button(self.instances_card, "Editar instancia")
        self.activate_instance_button = create_secondary_button(self.instances_card, "Activar instancia")
        self.deactivate_instance_button = create_warning_button(self.instances_card, "Desactivar instancia")
        self.instances_card.add(_button_row(
            self.instances_card, self.new_instance_button, self.edit_instance_button,
            self.activate_instance_button, self.deactivate_instance_button,
        ))

        self.instances_card.add(QLabel("Credenciales:", self.instances_card))
        self.credentials_table = StandardTable(_CREDENTIAL_COLUMNS, self.instances_card)
        self.credentials_table.setAccessibleName("Credenciales de la instancia seleccionada")
        self.instances_card.add(self.credentials_table)
        self.set_credential_button = create_secondary_button(self.instances_card, "Configurar credencial")
        self.instances_card.add(_button_row(self.instances_card, self.set_credential_button))

        self.layout().addWidget(self.instances_card)

        self.new_instance_button.clicked.connect(self._on_new_instance)
        self.edit_instance_button.clicked.connect(self._on_edit_instance)
        self.activate_instance_button.clicked.connect(lambda: self._on_change_instance_status("ACTIVATE"))
        self.deactivate_instance_button.clicked.connect(lambda: self._on_change_instance_status("DEACTIVATE"))
        self.set_credential_button.clicked.connect(self._on_set_credential)
        self.instances_table.itemSelectionChanged.connect(self._on_instance_selected)

    def _reload_instances(self) -> None:
        instances = (
            self._presenter.list_integration_instances(self._selected_definition_id)
            if self._selected_definition_id else ()
        )
        self._instances_by_id = {i.entity_id: i for i in instances}
        rows = [
            [i.name, ", ".join(f"{k}={v}" for k, v in i.config.items()), "Sí" if i.active else "No"]
            for i in instances
        ]
        self.instances_table.load_rows(rows, row_ids=[i.entity_id for i in instances])
        if self.instances_empty is not None:
            self.instances_empty.setParent(None)
            self.instances_empty = None
        if not rows:
            message = (
                "Selecciona una definición para ver sus instancias." if not self._selected_definition_id
                else "Esta definición no tiene instancias."
            )
            self.instances_empty = create_state_widget(ViewState.EMPTY, self.instances_card, message=message)
            self.instances_card.add(self.instances_empty)
        self.instances_table.setVisible(bool(rows))
        self._reload_credentials()

    def _on_instance_selected(self) -> None:
        self._selected_instance_id = self.instances_table.selected_row_id()
        self._reload_credentials()
        self._reload_webhooks()
        self._reload_health()

    def _reload_credentials(self) -> None:
        instance = self._instances_by_id.get(self._selected_instance_id)
        definition = self._definitions_by_id.get(self._selected_definition_id)
        rows = []
        row_ids = []
        if instance is not None and definition is not None:
            for credential_name in definition.required_credential_names:
                reference = instance.credential_references.get(credential_name)
                status = self._presenter.get_credential_status(reference)
                rows.append([credential_name, status])
                row_ids.append(credential_name)
        self.credentials_table.load_rows(rows, row_ids=row_ids)
        self.credentials_table.setVisible(bool(rows))

    def _selected_definition(self):
        if not self._selected_definition_id:
            QMessageBox.warning(self, "Integraciones", "Selecciona una definición primero.")
            return None
        return self._selected_definition_id

    def _selected_instance(self):
        if not self._selected_instance_id:
            QMessageBox.warning(self, "Integraciones", "Selecciona una instancia primero.")
            return None
        return self._selected_instance_id

    def _on_new_instance(self) -> None:
        if not self._selected_definition():
            return
        dlg = IntegrationInstanceCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Integraciones", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.create_integration_instance(
            definition_id=self._selected_definition_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_instances()

    def _on_edit_instance(self) -> None:
        instance_id = self._selected_instance()
        if not instance_id:
            return
        instance = self._instances_by_id.get(instance_id)
        if instance is None:
            QMessageBox.warning(self, "Integraciones", "La instancia ya no existe.")
            return
        dlg = IntegrationInstanceEditDialog(self, name=instance.name, config=instance.config)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Integraciones", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_integration_instance(instance_id=instance_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_instances()

    def _on_change_instance_status(self, action: str) -> None:
        instance_id = self._selected_instance()
        if not instance_id:
            return
        ok, message = self._presenter.change_integration_instance_status(instance_id=instance_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_instances()

    def _on_set_credential(self) -> None:
        instance_id = self._selected_instance()
        if not instance_id:
            return
        row_id = self.credentials_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Integraciones", "Selecciona una credencial primero.")
            return
        instance = self._instances_by_id.get(instance_id)
        existing_reference = instance.credential_references.get(row_id) if instance else ""
        dlg = SetCredentialDialog(self, credential_name=row_id, secret_name=existing_reference or "")
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.set_integration_instance_credential(instance_id=instance_id, **dlg.values())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_credentials()

    # ── Webhooks ─────────────────────────────────────────────────────────

    def _build_webhooks_card(self) -> None:
        self.webhooks_card = SectionCard(self, title="Webhooks")
        self.webhooks_table = StandardTable(_WEBHOOK_COLUMNS, self.webhooks_card)
        self.webhooks_table.setAccessibleName("Webhooks de la instancia seleccionada")
        self.webhooks_card.add(self.webhooks_table)
        self.webhooks_empty = None

        self.new_webhook_button = create_primary_button(self.webhooks_card, "Nuevo webhook")
        self.activate_webhook_button = create_secondary_button(self.webhooks_card, "Activar")
        self.deactivate_webhook_button = create_warning_button(self.webhooks_card, "Desactivar")
        self.webhooks_card.add(_button_row(
            self.webhooks_card, self.new_webhook_button, self.activate_webhook_button,
            self.deactivate_webhook_button,
        ))
        self.layout().addWidget(self.webhooks_card)

        self.new_webhook_button.clicked.connect(self._on_new_webhook)
        self.activate_webhook_button.clicked.connect(lambda: self._on_change_webhook_status("ACTIVATE"))
        self.deactivate_webhook_button.clicked.connect(lambda: self._on_change_webhook_status("DEACTIVATE"))

    def _reload_webhooks(self) -> None:
        endpoints = (
            self._presenter.list_webhook_endpoints(self._selected_instance_id)
            if self._selected_instance_id else ()
        )
        rows = [[e.code, e.path, e.signature_scheme, "Sí" if e.active else "No"] for e in endpoints]
        self.webhooks_table.load_rows(rows, row_ids=[e.entity_id for e in endpoints])
        if self.webhooks_empty is not None:
            self.webhooks_empty.setParent(None)
            self.webhooks_empty = None
        if not rows:
            message = (
                "Selecciona una instancia para ver sus webhooks." if not self._selected_instance_id
                else "Esta instancia no tiene webhooks."
            )
            self.webhooks_empty = create_state_widget(ViewState.EMPTY, self.webhooks_card, message=message)
            self.webhooks_card.add(self.webhooks_empty)
        self.webhooks_table.setVisible(bool(rows))

    def _on_new_webhook(self) -> None:
        instance_id = self._selected_instance()
        if not instance_id:
            return
        dlg = WebhookEndpointCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["path"]:
            QMessageBox.warning(self, "Integraciones", "Código y ruta son obligatorios.")
            return
        ok, message = self._presenter.create_webhook_endpoint(instance_id=instance_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_webhooks()

    def _on_change_webhook_status(self, action: str) -> None:
        endpoint_id = self.webhooks_table.selected_row_id()
        if not endpoint_id:
            QMessageBox.warning(self, "Integraciones", "Selecciona un webhook primero.")
            return
        ok, message = self._presenter.change_webhook_endpoint_status(endpoint_id=endpoint_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_webhooks()

    # ── Salud ────────────────────────────────────────────────────────────

    def _build_health_card(self) -> None:
        self.health_card = SectionCard(self, title="Salud")
        self.health_status_label = QLabel("Estado: —", self.health_card)
        self.health_card.add(self.health_status_label)
        self.health_table = StandardTable(_HEALTH_COLUMNS, self.health_card)
        self.health_table.setAccessibleName("Historial de chequeos de la instancia seleccionada")
        self.health_card.add(self.health_table)
        self.health_empty = None

        self.record_health_button = create_secondary_button(self.health_card, "Registrar chequeo")
        self.health_card.add(_button_row(self.health_card, self.record_health_button))
        self.layout().addWidget(self.health_card)

        self.record_health_button.clicked.connect(self._on_record_health_check)

    def _reload_health(self) -> None:
        if not self._selected_instance_id:
            self.health_status_label.setText("Estado: —")
            checks = ()
        else:
            status = self._presenter.get_integration_health_status(self._selected_instance_id)
            self.health_status_label.setText(f"Estado: {status}")
            checks = self._presenter.list_integration_health_checks(self._selected_instance_id)
        rows = [["Éxito" if c.success else "Falla", c.message or "—", c.checked_at] for c in checks]
        self.health_table.load_rows(rows, row_ids=[c.entity_id for c in checks])
        if self.health_empty is not None:
            self.health_empty.setParent(None)
            self.health_empty = None
        if not rows:
            message = (
                "Selecciona una instancia para ver su historial de salud." if not self._selected_instance_id
                else "Sin chequeos registrados todavía."
            )
            self.health_empty = create_state_widget(ViewState.EMPTY, self.health_card, message=message)
            self.health_card.add(self.health_empty)
        self.health_table.setVisible(bool(rows))

    def _on_record_health_check(self) -> None:
        instance_id = self._selected_instance()
        if not instance_id:
            return
        dlg = RecordHealthCheckDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.record_integration_health_check(instance_id=instance_id, **dlg.values())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self._reload_health()

    # ── Definiciones ─────────────────────────────────────────────────────

    def _on_new_definition(self) -> None:
        dlg = IntegrationDefinitionCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["name"] or not values["category"]:
            QMessageBox.warning(self, "Integraciones", "Código, nombre y categoría son obligatorios.")
            return
        ok, message = self._presenter.create_integration_definition(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_definition(self) -> None:
        definition_id = self._selected_definition()
        if not definition_id:
            return
        definitions = {d.entity_id: d for d in self._presenter.list_integration_definitions()}
        definition = definitions.get(definition_id)
        if definition is None:
            QMessageBox.warning(self, "Integraciones", "La definición ya no existe.")
            return
        dlg = IntegrationDefinitionEditDialog(
            self, name=definition.name, required_credential_names=definition.required_credential_names)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Integraciones", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_integration_definition(definition_id=definition_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_definition_status(self, action: str) -> None:
        definition_id = self._selected_definition()
        if not definition_id:
            return
        ok, message = self._presenter.change_integration_definition_status(
            definition_id=definition_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Integraciones", message)
        if ok:
            self.reload(self.search.text())


__all__ = ["IntegracionesPage"]
