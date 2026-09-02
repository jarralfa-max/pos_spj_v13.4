"""Notificaciones page — SET-20 cutover, real CRUD for the Accounts/
Templates/Routing pillars. Main table lists `NotificationRoute`s
(already the section's real content, per the existing
`_page_notificaciones` query); two always-visible cards below —
"Cuentas" and "Plantillas" — provide the pickers a new Route needs, same
non-cascaded "campaign card alongside the main table" shape
`documentos_page.py` already established for Marketing campaigns
(SET-13), rather than a selection cascade (a Route composes an existing
Account + Template, it isn't a child of either).
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_primary_button, create_secondary_button,
    create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    NotificationAccountCreateDialog,
    NotificationAccountEditDialog,
    NotificationRouteCreateDialog,
    NotificationTemplateCreateDialog,
    NotificationTemplateEditDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_ACCOUNT_COLUMNS = [
    ColumnSpec("Canal"), ColumnSpec("Nombre"), ColumnSpec("Credencial"), ColumnSpec("Activo", "status"),
]
_TEMPLATE_COLUMNS = [
    ColumnSpec("Código"), ColumnSpec("Canal"), ColumnSpec("Idioma"), ColumnSpec("Parámetros"),
    ColumnSpec("Activo", "status"),
]


def _button_row(parent, *buttons):
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Spacing.SM)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


class NotificacionesPage(ConfiguracionWorkspacePage):
    page_id = "config_notificaciones"
    title = "Notificaciones"
    subtitle = "Cuentas, plantillas y ruteo de notificaciones."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._accounts_by_id: dict = {}
        self._templates_by_id: dict = {}

        self.new_route_button = create_primary_button(self, "Nueva ruta")
        self.activate_route_button = create_secondary_button(self, "Activar ruta")
        self.deactivate_route_button = create_warning_button(self, "Desactivar ruta")
        route_actions = _button_row(
            self, self.new_route_button, self.activate_route_button, self.deactivate_route_button,
        )
        self.layout().insertWidget(1, route_actions)

        self.new_route_button.clicked.connect(self._on_new_route)
        self.activate_route_button.clicked.connect(lambda: self._on_change_route_status("ACTIVATE"))
        self.deactivate_route_button.clicked.connect(lambda: self._on_change_route_status("DEACTIVATE"))

        self._build_accounts_card()
        self._build_templates_card()

        self._reload_accounts()
        self._reload_templates()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        self._reload_accounts()
        self._reload_templates()

    def _selected_route_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Notificaciones", "Selecciona una ruta primero.")
        return row_id

    def _on_new_route(self) -> None:
        dlg = NotificationRouteCreateDialog(
            self, template_options=self._presenter.list_notification_templates(),
            account_options=self._presenter.list_notification_accounts(),
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["event_code"] or not values["template_id"] or not values["account_id"]:
            QMessageBox.warning(self, "Notificaciones", "Evento, plantilla y cuenta son obligatorios.")
            return
        ok, message = self._presenter.create_notification_route(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_route_status(self, action: str) -> None:
        route_id = self._selected_route_id()
        if not route_id:
            return
        ok, message = self._presenter.change_notification_route_status(route_id=route_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self.reload(self.search.text())

    # ── Cuentas ──────────────────────────────────────────────────────────

    def _build_accounts_card(self) -> None:
        self.accounts_card = SectionCard(self, title="Cuentas")
        self.accounts_table = StandardTable(_ACCOUNT_COLUMNS, self.accounts_card)
        self.accounts_table.setAccessibleName("Cuentas de notificación")
        self.accounts_card.add(self.accounts_table)
        self.accounts_empty = None

        self.new_account_button = create_primary_button(self.accounts_card, "Nueva cuenta")
        self.edit_account_button = create_secondary_button(self.accounts_card, "Editar cuenta")
        self.activate_account_button = create_secondary_button(self.accounts_card, "Activar")
        self.deactivate_account_button = create_warning_button(self.accounts_card, "Desactivar")
        self.accounts_card.add(_button_row(
            self.accounts_card, self.new_account_button, self.edit_account_button,
            self.activate_account_button, self.deactivate_account_button,
        ))
        self.layout().addWidget(self.accounts_card)

        self.new_account_button.clicked.connect(self._on_new_account)
        self.edit_account_button.clicked.connect(self._on_edit_account)
        self.activate_account_button.clicked.connect(lambda: self._on_change_account_status("ACTIVATE"))
        self.deactivate_account_button.clicked.connect(lambda: self._on_change_account_status("DEACTIVATE"))

    def _reload_accounts(self) -> None:
        accounts = self._presenter.list_notification_accounts()
        self._accounts_by_id = {a.entity_id: a for a in accounts}
        rows = [
            [a.channel, a.name, a.credential_reference or "—", "Sí" if a.active else "No"]
            for a in accounts
        ]
        self.accounts_table.load_rows(rows, row_ids=[a.entity_id for a in accounts])
        if self.accounts_empty is not None:
            self.accounts_empty.setParent(None)
            self.accounts_empty = None
        if not rows:
            self.accounts_empty = create_state_widget(
                ViewState.EMPTY, self.accounts_card, message="No hay cuentas de notificación todavía.")
            self.accounts_card.add(self.accounts_empty)
        self.accounts_table.setVisible(bool(rows))

    def _selected_account_id(self) -> str | None:
        row_id = self.accounts_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Notificaciones", "Selecciona una cuenta primero.")
        return row_id

    def _on_new_account(self) -> None:
        dlg = NotificationAccountCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["channel"] or not values["name"]:
            QMessageBox.warning(self, "Notificaciones", "Canal y nombre son obligatorios.")
            return
        ok, message = self._presenter.create_notification_account(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self._reload_accounts()

    def _on_edit_account(self) -> None:
        account_id = self._selected_account_id()
        if not account_id:
            return
        account = self._accounts_by_id.get(account_id)
        if account is None:
            QMessageBox.warning(self, "Notificaciones", "La cuenta ya no existe.")
            return
        dlg = NotificationAccountEditDialog(
            self, name=account.name, credential_reference=account.credential_reference)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Notificaciones", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_notification_account(account_id=account_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self._reload_accounts()

    def _on_change_account_status(self, action: str) -> None:
        account_id = self._selected_account_id()
        if not account_id:
            return
        ok, message = self._presenter.change_notification_account_status(account_id=account_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self._reload_accounts()

    # ── Plantillas ───────────────────────────────────────────────────────

    def _build_templates_card(self) -> None:
        self.templates_card = SectionCard(self, title="Plantillas")
        self.templates_table = StandardTable(_TEMPLATE_COLUMNS, self.templates_card)
        self.templates_table.setAccessibleName("Plantillas de notificación")
        self.templates_card.add(self.templates_table)
        self.templates_empty = None

        self.new_template_button = create_primary_button(self.templates_card, "Nueva plantilla")
        self.edit_template_button = create_secondary_button(self.templates_card, "Editar parámetros")
        self.activate_template_button = create_secondary_button(self.templates_card, "Activar")
        self.deactivate_template_button = create_warning_button(self.templates_card, "Desactivar")
        self.templates_card.add(_button_row(
            self.templates_card, self.new_template_button, self.edit_template_button,
            self.activate_template_button, self.deactivate_template_button,
        ))
        self.layout().addWidget(self.templates_card)

        self.new_template_button.clicked.connect(self._on_new_template)
        self.edit_template_button.clicked.connect(self._on_edit_template)
        self.activate_template_button.clicked.connect(lambda: self._on_change_template_status("ACTIVATE"))
        self.deactivate_template_button.clicked.connect(lambda: self._on_change_template_status("DEACTIVATE"))

    def _reload_templates(self) -> None:
        templates = self._presenter.list_notification_templates()
        self._templates_by_id = {t.entity_id: t for t in templates}
        rows = [
            [t.code, t.channel, t.language, ", ".join(t.parameter_names) or "—", "Sí" if t.active else "No"]
            for t in templates
        ]
        self.templates_table.load_rows(rows, row_ids=[t.entity_id for t in templates])
        if self.templates_empty is not None:
            self.templates_empty.setParent(None)
            self.templates_empty = None
        if not rows:
            self.templates_empty = create_state_widget(
                ViewState.EMPTY, self.templates_card, message="No hay plantillas de notificación todavía.")
            self.templates_card.add(self.templates_empty)
        self.templates_table.setVisible(bool(rows))

    def _selected_template_id(self) -> str | None:
        row_id = self.templates_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Notificaciones", "Selecciona una plantilla primero.")
        return row_id

    def _on_new_template(self) -> None:
        dlg = NotificationTemplateCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["channel"] or not values["language"]:
            QMessageBox.warning(self, "Notificaciones", "Código, canal e idioma son obligatorios.")
            return
        ok, message = self._presenter.create_notification_template(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self._reload_templates()

    def _on_edit_template(self) -> None:
        template_id = self._selected_template_id()
        if not template_id:
            return
        template = self._templates_by_id.get(template_id)
        if template is None:
            QMessageBox.warning(self, "Notificaciones", "La plantilla ya no existe.")
            return
        dlg = NotificationTemplateEditDialog(self, parameter_names=template.parameter_names)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.update_notification_template(template_id=template_id, **dlg.values())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self._reload_templates()

    def _on_change_template_status(self, action: str) -> None:
        template_id = self._selected_template_id()
        if not template_id:
            return
        ok, message = self._presenter.change_notification_template_status(template_id=template_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Notificaciones", message)
        if ok:
            self._reload_templates()


__all__ = ["NotificacionesPage"]
