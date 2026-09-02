"""Documentos page — third section with REAL CRUD wired for
Configuración (SET-25 follow-up #3): create a document template family
(with its first draft version), create new versions, and drive the
7-state approval lifecycle (enviar a aprobación/aprobar/rechazar/
activar/desactivar/expirar/archivar).

Selecting a template row reloads its versions into the secondary table —
`self.table` is rebuilt on every `reload()` (see `base_page.py`), so the
selection signal is reconnected each time rather than once in `__init__`.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    DocumentTemplateCreateDialog,
    DocumentTemplateEditDialog,
    MarketingCampaignCreateDialog,
    MarketingCampaignEditDialog,
    NewTemplateVersionDialog,
    RejectTemplateVersionDialog,
    rules_to_text,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_VERSION_COLUMNS = [
    ColumnSpec("Versión", "numeric"), ColumnSpec("Estado", "status"), ColumnSpec("Motivo"),
    ColumnSpec("Creado por"),
]

_CAMPAIGN_COLUMNS = [
    ColumnSpec("Código"), ColumnSpec("Categoría"), ColumnSpec("Mensaje"), ColumnSpec("Prioridad", "numeric"),
    ColumnSpec("Requiere cliente"), ColumnSpec("Activa", "status"),
]


class DocumentosPage(ConfiguracionWorkspacePage):
    page_id = "config_documentos"
    title = "Documentos"
    subtitle = "Plantillas de tickets, etiquetas y numeración."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._selected_template_id: str | None = None

        template_actions = QWidget(self)
        template_actions_layout = QHBoxLayout(template_actions)
        template_actions_layout.setContentsMargins(0, 0, 0, 0)
        template_actions_layout.setSpacing(Spacing.SM)
        self.new_template_button = create_primary_button(template_actions, "Nueva plantilla")
        self.edit_template_button = create_secondary_button(template_actions, "Editar plantilla")
        self.activate_template_button = create_primary_button(template_actions, "Activar plantilla")
        self.deactivate_template_button = create_warning_button(template_actions, "Desactivar plantilla")
        for button in (
            self.new_template_button, self.edit_template_button, self.activate_template_button,
            self.deactivate_template_button,
        ):
            template_actions_layout.addWidget(button)
        template_actions_layout.addStretch(1)
        self.layout().insertWidget(1, template_actions)

        self.new_template_button.clicked.connect(self._on_new_template)
        self.edit_template_button.clicked.connect(self._on_edit_template)
        self.activate_template_button.clicked.connect(lambda: self._on_change_template_status("ACTIVATE"))
        self.deactivate_template_button.clicked.connect(lambda: self._on_change_template_status("DEACTIVATE"))

        self.versions_card = SectionCard(self, title="Versiones")
        self.versions_table = StandardTable(_VERSION_COLUMNS, self.versions_card)
        self.versions_table.setAccessibleName("Versiones de la plantilla seleccionada")
        self.versions_card.add(self.versions_table)
        self.versions_empty = None

        actions = QWidget(self.versions_card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Spacing.SM)
        self.new_version_button = create_secondary_button(actions, "Nueva versión")
        self.submit_button = create_secondary_button(actions, "Enviar a aprobación")
        self.approve_button = create_primary_button(actions, "Aprobar")
        self.reject_button = create_danger_button(actions, "Rechazar")
        self.activate_button = create_primary_button(actions, "Activar")
        self.deactivate_button = create_warning_button(actions, "Desactivar")
        self.expire_button = create_warning_button(actions, "Expirar")
        self.archive_button = create_secondary_button(actions, "Archivar")
        for button in (
            self.new_version_button, self.submit_button, self.approve_button, self.reject_button,
            self.activate_button, self.deactivate_button, self.expire_button, self.archive_button,
        ):
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        self.versions_card.add(actions)

        self.layout().addWidget(self.versions_card)

        self.new_version_button.clicked.connect(self._on_new_version)
        self.submit_button.clicked.connect(lambda: self._on_change_status("SUBMIT_FOR_APPROVAL"))
        self.approve_button.clicked.connect(lambda: self._on_change_status("APPROVE"))
        self.reject_button.clicked.connect(self._on_reject)
        self.activate_button.clicked.connect(lambda: self._on_change_status("ACTIVATE"))
        self.deactivate_button.clicked.connect(lambda: self._on_change_status("DEACTIVATE"))
        self.expire_button.clicked.connect(lambda: self._on_change_status("EXPIRE"))
        self.archive_button.clicked.connect(lambda: self._on_change_status("ARCHIVE"))

        self.campaigns_card = SectionCard(self, title="Campañas de marketing")
        self.campaigns_table = StandardTable(_CAMPAIGN_COLUMNS, self.campaigns_card)
        self.campaigns_table.setAccessibleName("Campañas de marketing en tickets")
        self.campaigns_card.add(self.campaigns_table)
        self.campaigns_empty = None

        campaign_actions = QWidget(self.campaigns_card)
        campaign_actions_layout = QHBoxLayout(campaign_actions)
        campaign_actions_layout.setContentsMargins(0, 0, 0, 0)
        campaign_actions_layout.setSpacing(Spacing.SM)
        self.new_campaign_button = create_primary_button(campaign_actions, "Nueva campaña")
        self.edit_campaign_button = create_secondary_button(campaign_actions, "Editar campaña")
        self.activate_campaign_button = create_secondary_button(campaign_actions, "Activar campaña")
        self.deactivate_campaign_button = create_warning_button(campaign_actions, "Desactivar campaña")
        for button in (
            self.new_campaign_button, self.edit_campaign_button, self.activate_campaign_button,
            self.deactivate_campaign_button,
        ):
            campaign_actions_layout.addWidget(button)
        campaign_actions_layout.addStretch(1)
        self.campaigns_card.add(campaign_actions)

        self.layout().addWidget(self.campaigns_card)

        self.new_campaign_button.clicked.connect(self._on_new_campaign)
        self.edit_campaign_button.clicked.connect(self._on_edit_campaign)
        self.activate_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("ACTIVATE"))
        self.deactivate_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("DEACTIVATE"))

        self._campaigns_by_id: dict = {}
        self._reload_versions()
        self._reload_campaigns()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        if self.table is not None:
            self.table.itemSelectionChanged.connect(self._on_template_selected)
        self._selected_template_id = None
        self._reload_versions()
        self._reload_campaigns()

    def _on_template_selected(self) -> None:
        self._selected_template_id = self.table.selected_row_id() if self.table is not None else None
        self._reload_versions()

    def _reload_versions(self) -> None:
        versions = (
            self._presenter.list_template_versions(self._selected_template_id)
            if self._selected_template_id else ()
        )
        rows = [[str(v.version), v.status, v.reason or "—", v.created_by_user_id or "—"] for v in versions]
        self.versions_table.load_rows(rows, row_ids=[v.entity_id for v in versions])
        if self.versions_empty is not None:
            self.versions_empty.setParent(None)
            self.versions_empty = None
        if not rows:
            message = (
                "Selecciona una plantilla para ver sus versiones." if not self._selected_template_id
                else "Esta plantilla no tiene versiones."
            )
            self.versions_empty = create_state_widget(ViewState.EMPTY, self.versions_card, message=message)
            self.versions_card.add(self.versions_empty)
        self.versions_table.setVisible(bool(rows))

    def _selected_version_id(self) -> str | None:
        row_id = self.versions_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Documentos", "Selecciona una versión primero.")
        return row_id

    def _on_new_template(self) -> None:
        dlg = DocumentTemplateCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"] or not values["document_type"] or not values["module"] or not values["content_format"] or not values["content"]:
            QMessageBox.warning(
                self, "Documentos", "Nombre, tipo, módulo, formato y contenido son obligatorios.",
            )
            return
        ok, message = self._presenter.create_document_template(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_template(self) -> None:
        if not self._selected_template_id:
            QMessageBox.warning(self, "Documentos", "Selecciona una plantilla primero.")
            return
        template = self._presenter.get_template(self._selected_template_id)
        if template is None:
            QMessageBox.warning(self, "Documentos", "La plantilla ya no existe.")
            return
        dlg = DocumentTemplateEditDialog(
            self, name=template.name, module=template.module, description=template.description,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"] or not values["module"]:
            QMessageBox.warning(self, "Documentos", "Nombre y módulo son obligatorios.")
            return
        ok, message = self._presenter.update_document_template(
            template_id=self._selected_template_id, **values,
        )
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_template_status(self, action: str) -> None:
        if not self._selected_template_id:
            QMessageBox.warning(self, "Documentos", "Selecciona una plantilla primero.")
            return
        ok, message = self._presenter.change_document_template_status(
            template_id=self._selected_template_id, action=action,
        )
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self.reload(self.search.text())

    def _on_new_version(self) -> None:
        if not self._selected_template_id:
            QMessageBox.warning(self, "Documentos", "Selecciona una plantilla primero.")
            return
        version_id = self._selected_version_id()
        if not version_id:
            return
        dlg = NewTemplateVersionDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        content = dlg.content_text()
        if not content:
            QMessageBox.warning(self, "Documentos", "El contenido no puede estar vacío.")
            return
        ok, message = self._presenter.create_next_template_version(version_id=version_id, content=content)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self._reload_versions()

    def _on_reject(self) -> None:
        version_id = self._selected_version_id()
        if not version_id:
            return
        dlg = RejectTemplateVersionDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.change_template_version_status(
            version_id=version_id, action="REJECT", reason=dlg.reason_text(),
        )
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self._reload_versions()

    def _on_change_status(self, action: str) -> None:
        version_id = self._selected_version_id()
        if not version_id:
            return
        ok, message = self._presenter.change_template_version_status(version_id=version_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self._reload_versions()

    def _reload_campaigns(self) -> None:
        campaigns = self._presenter.list_marketing_campaigns()
        self._campaigns_by_id = {c.entity_id: c for c in campaigns}
        rows = [
            [
                c.code, c.category, c.message_template, str(c.priority),
                "Sí" if c.requires_customer else "No", "Sí" if c.active else "No",
            ]
            for c in campaigns
        ]
        self.campaigns_table.load_rows(rows, row_ids=[c.entity_id for c in campaigns])
        if self.campaigns_empty is not None:
            self.campaigns_empty.setParent(None)
            self.campaigns_empty = None
        if not rows:
            self.campaigns_empty = create_state_widget(
                ViewState.EMPTY, self.campaigns_card, message="No hay campañas de marketing todavía.",
            )
            self.campaigns_card.add(self.campaigns_empty)
        self.campaigns_table.setVisible(bool(rows))

    def _selected_campaign_id(self) -> str | None:
        row_id = self.campaigns_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Documentos", "Selecciona una campaña primero.")
        return row_id

    def _on_new_campaign(self) -> None:
        dlg = MarketingCampaignCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["category"] or not values["message_template"]:
            QMessageBox.warning(self, "Documentos", "Código, categoría y mensaje son obligatorios.")
            return
        ok, message = self._presenter.create_marketing_campaign(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self._reload_campaigns()

    def _on_edit_campaign(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            return
        campaign = self._campaigns_by_id.get(campaign_id)
        if campaign is None:
            QMessageBox.warning(self, "Documentos", "La campaña ya no existe.")
            return
        dlg = MarketingCampaignEditDialog(
            self, message_template=campaign.message_template, priority=campaign.priority,
            requires_customer=campaign.requires_customer, rules_text=rules_to_text(campaign.rules),
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["message_template"]:
            QMessageBox.warning(self, "Documentos", "El mensaje no puede estar vacío.")
            return
        ok, message = self._presenter.update_marketing_campaign(campaign_id=campaign_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self._reload_campaigns()

    def _on_change_campaign_status(self, action: str) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            return
        ok, message = self._presenter.change_marketing_campaign_status(campaign_id=campaign_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Documentos", message)
        if ok:
            self._reload_campaigns()


__all__ = ["DocumentosPage"]
