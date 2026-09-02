"""Feature Flags page — the base inherited table (title "Feature Flags",
`_page_feature_flags` query) is now the real Flags admin table
(create/edit/activate/deactivate + "Solicitar cambio"), same "reuse the
inherited table as the main interactive table" shape
`NotificacionesPage` established for its Routes table (SET-20) — this
keeps the search box meaningful (it filters Flags) instead of adding a
redundant second table. A "Reglas activas" card, driven by the Flags
table's current selection, shows that flag's `FeatureFlagRule`s
read-only (rules are only ever created through the approval flow below,
by design — segregation of duties, §59). "Solicitudes pendientes" +
approve/reject/apply stays exactly as it shipped in SET-21.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    FeatureFlagCreateDialog,
    FeatureFlagEditDialog,
    RejectChangeRequestDialog,
    RequestFeatureFlagChangeDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_REQUEST_COLUMNS = [
    ColumnSpec("Flag"), ColumnSpec("Alcance"), ColumnSpec("Propuesto", "status"),
    ColumnSpec("Solicitado por"),
]
_RULE_COLUMNS = [
    ColumnSpec("Alcance"), ColumnSpec("ID de alcance"), ColumnSpec("Habilitada", "status"),
    ColumnSpec("Rollout (%)", "numeric"), ColumnSpec("Activa", "status"),
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


class FeatureFlagsPage(ConfiguracionWorkspacePage):
    page_id = "config_feature_flags"
    title = "Feature Flags"
    subtitle = "Flags, reglas activas y solicitudes de cambio pendientes de aprobación."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._flags_by_id: dict = {}

        self.new_flag_button = create_primary_button(self, "Nueva flag")
        self.edit_flag_button = create_secondary_button(self, "Editar")
        self.activate_flag_button = create_secondary_button(self, "Activar")
        self.deactivate_flag_button = create_warning_button(self, "Desactivar")
        self.request_change_button = create_secondary_button(self, "Solicitar cambio")
        flag_actions = _button_row(
            self, self.new_flag_button, self.edit_flag_button, self.activate_flag_button,
            self.deactivate_flag_button, self.request_change_button,
        )
        self.layout().insertWidget(1, flag_actions)

        self.new_flag_button.clicked.connect(self._on_new_flag)
        self.edit_flag_button.clicked.connect(self._on_edit_flag)
        self.activate_flag_button.clicked.connect(lambda: self._on_change_flag_status("ACTIVATE"))
        self.deactivate_flag_button.clicked.connect(lambda: self._on_change_flag_status("DEACTIVATE"))
        self.request_change_button.clicked.connect(self._on_request_change)

        self._build_rules_card()
        self._build_requests_card()

    # ── Flags (base inherited table) ────────────────────────────────────────

    def reload(self, search: str = "") -> None:
        super().reload(search)
        if self.table is not None:
            self.table.itemSelectionChanged.connect(self._on_flag_selection_changed)
        self._flags_by_id = {f.entity_id: f for f in self._presenter.list_feature_flags()}
        self._reload_rules()
        self._reload_requests()

    def _selected_flag_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Feature Flags", "Selecciona un flag primero.")
        return row_id

    def _on_new_flag(self) -> None:
        dlg = FeatureFlagCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["name"]:
            QMessageBox.warning(self, "Feature Flags", "Código y nombre son obligatorios.")
            return
        ok, message = self._presenter.create_feature_flag(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_flag(self) -> None:
        flag_id = self._selected_flag_id()
        if not flag_id:
            return
        flag = self._flags_by_id.get(flag_id)
        if flag is None:
            QMessageBox.warning(self, "Feature Flags", "El flag ya no existe.")
            return
        dlg = FeatureFlagEditDialog(
            self, name=flag.name, description=flag.description, default_enabled=flag.default_enabled)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Feature Flags", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_feature_flag(flag_id=flag_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_flag_status(self, action: str) -> None:
        flag_id = self._selected_flag_id()
        if not flag_id:
            return
        ok, message = self._presenter.change_feature_flag_status(flag_id=flag_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self.reload(self.search.text())

    def _on_request_change(self) -> None:
        dlg = RequestFeatureFlagChangeDialog(self, flag_options=self._presenter.list_feature_flags())
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["flag_id"] or not values["scope_type"]:
            QMessageBox.warning(self, "Feature Flags", "Selecciona un flag y un alcance.")
            return
        ok, message = self._presenter.request_feature_flag_change(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self._reload_requests()

    # ── Reglas activas (read-only, driven by Flags selection) ──────────────

    def _build_rules_card(self) -> None:
        self.rules_card = SectionCard(self, title="Reglas activas")
        self.rules_table = StandardTable(_RULE_COLUMNS, self.rules_card)
        self.rules_table.setAccessibleName("Reglas activas del flag seleccionado")
        self.rules_card.add(self.rules_table)
        self.rules_empty = None
        self.layout().addWidget(self.rules_card)
        self._reload_rules()

    def _on_flag_selection_changed(self) -> None:
        self._reload_rules()

    def _reload_rules(self) -> None:
        flag_id = self.table.selected_row_id() if self.table is not None else None
        rules = self._presenter.list_feature_flag_rules(flag_id) if flag_id else ()
        rows = [
            [r.scope_type, r.scope_id or "—", "Sí" if r.enabled else "No", str(r.rollout_percentage),
             "Sí" if r.active else "No"]
            for r in rules
        ]
        self.rules_table.load_rows(rows, row_ids=[r.entity_id for r in rules])
        if self.rules_empty is not None:
            self.rules_empty.setParent(None)
            self.rules_empty = None
        if not rows:
            message = "Selecciona un flag para ver sus reglas." if not flag_id else "Este flag no tiene reglas."
            self.rules_empty = create_state_widget(ViewState.EMPTY, self.rules_card, message=message)
            self.rules_card.add(self.rules_empty)
        self.rules_table.setVisible(bool(rows))

    # ── Solicitudes pendientes (Approve/Reject/Apply — SET-21 original) ────

    def _build_requests_card(self) -> None:
        self.requests_card = SectionCard(self, title="Solicitudes pendientes")
        self.requests_table = StandardTable(_REQUEST_COLUMNS, self.requests_card)
        self.requests_table.setAccessibleName("Solicitudes de cambio de feature flags pendientes")
        self.requests_card.add(self.requests_table)
        self.requests_empty = None

        actions = QWidget(self.requests_card)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Spacing.SM)
        self.approve_button = create_primary_button(actions, "Aprobar")
        self.apply_button = create_secondary_button(actions, "Aplicar")
        self.reject_button = create_danger_button(actions, "Rechazar")
        for button in (self.approve_button, self.apply_button, self.reject_button):
            actions_layout.addWidget(button)
        actions_layout.addStretch(1)
        self.requests_card.add(actions)

        self.layout().addWidget(self.requests_card)
        self.approve_button.clicked.connect(self._on_approve)
        self.reject_button.clicked.connect(self._on_reject)
        self.apply_button.clicked.connect(self._on_apply)
        self._reload_requests()

    def _reload_requests(self) -> None:
        requests = self._presenter.list_pending_feature_flag_change_requests()
        rows = [[r.flag_code, r.scope, r.proposed_enabled, r.requested_by] for r in requests]
        self.requests_table.load_rows(rows, row_ids=[r.entity_id for r in requests])
        if self.requests_empty is not None:
            self.requests_empty.setParent(None)
            self.requests_empty = None
        if not rows:
            self.requests_empty = create_state_widget(
                ViewState.EMPTY, self.requests_card, message="No hay solicitudes pendientes.",
            )
            self.requests_card.add(self.requests_empty)
        self.requests_table.setVisible(bool(rows))

    def _selected_request_id(self) -> str | None:
        row_id = self.requests_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Feature Flags", "Selecciona una solicitud pendiente primero.")
        return row_id

    def _on_approve(self) -> None:
        request_id = self._selected_request_id()
        if not request_id:
            return
        ok, message = self._presenter.approve_feature_flag_change_request(request_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self._reload_requests()

    def _on_reject(self) -> None:
        request_id = self._selected_request_id()
        if not request_id:
            return
        dlg = RejectChangeRequestDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.reject_feature_flag_change_request(request_id, dlg.reason_text())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self._reload_requests()

    def _on_apply(self) -> None:
        request_id = self._selected_request_id()
        if not request_id:
            return
        ok, message = self._presenter.apply_feature_flag_change_request(request_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Feature Flags", message)
        if ok:
            self._reload_requests()
            self.reload(self.search.text())


__all__ = ["FeatureFlagsPage"]
