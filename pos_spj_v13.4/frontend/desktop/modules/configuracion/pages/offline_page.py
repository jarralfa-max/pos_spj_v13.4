"""Offline page — the base inherited table (title "Offline",
`_page_offline` query) is now the real Expiration Policies admin table
(create/edit/activate/deactivate), same "reuse the inherited table as
the main interactive table" shape `FeatureFlagsPage`/`AparienciaPage`
established this session. A second, independent "Caché por estación"
card lists `OfflineCacheEntry` rows — but stays PURELY READ-ONLY, no
create/edit/status buttons at all: a cache entry is a runtime artifact
meant to be written by a real offline-first read consumer, and no such
consumer exists in this repo (`sync/` is confirmed dead). Hand-authoring
one via a form would not reflect any real workflow, so none was built —
see `offline_management_use_cases.py`'s module docstring for the same
reasoning on the application side.

"Conflictos de sincronización" (SDLC-SYNC-002): hechos que el servidor central
guardó en conflicto y no llegan a sus libros. Se resuelven aquí, en la estación
(decisión del responsable, 2026-11-05), con motivo obligatorio.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_primary_button, create_secondary_button,
    create_state_widget, create_warning_button,
)
from frontend.desktop.components.dialogs import MessageDialog
from frontend.desktop.modules.configuracion.dialogs import (
    CacheExpirationPolicyCreateDialog,
    CacheExpirationPolicyEditDialog,
    ResolveReplicationConflictDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_CACHE_COLUMNS = [
    ColumnSpec("Tipo de entidad"), ColumnSpec("ID de entidad"), ColumnSpec("Estación"),
    ColumnSpec("Estado", "status"), ColumnSpec("Actualizado"),
]

_CACHE_EMPTY_MESSAGE = (
    "No hay entradas de caché. Las entradas las genera un consumidor de lectura offline en tiempo real; "
    "hoy no existe uno en este repositorio, por lo que esta lista estará vacía en producción actual."
)


_CONFLICT_COLUMNS = [
    ColumnSpec("Secuencia"), ColumnSpec("Contexto"), ColumnSpec("Evento"), ColumnSpec("Motivo"),
    ColumnSpec("Creado"),
]

_CONFLICT_EMPTY_MESSAGE = "No hay conflictos de sincronización pendientes."


def _button_row(parent, *buttons):
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Spacing.SM)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


class OfflinePage(ConfiguracionWorkspacePage):
    page_id = "config_offline"
    title = "Offline"
    subtitle = ("Políticas de expiración de caché, diagnóstico de caché por estación y "
                "conflictos de sincronización.")

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)

        self.new_policy_button = create_primary_button(self, "Nueva política")
        self.edit_policy_button = create_secondary_button(self, "Editar")
        self.activate_policy_button = create_secondary_button(self, "Activar")
        self.deactivate_policy_button = create_warning_button(self, "Desactivar")
        policy_actions = _button_row(
            self, self.new_policy_button, self.edit_policy_button, self.activate_policy_button,
            self.deactivate_policy_button,
        )
        self.layout().insertWidget(1, policy_actions)

        self.new_policy_button.clicked.connect(self._on_new_policy)
        self.edit_policy_button.clicked.connect(self._on_edit_policy)
        self.activate_policy_button.clicked.connect(lambda: self._on_change_policy_status("ACTIVATE"))
        self.deactivate_policy_button.clicked.connect(lambda: self._on_change_policy_status("DEACTIVATE"))

        self._policies_by_id: dict = {}
        self._build_cache_card()
        self._build_conflicts_card()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        self._policies_by_id = {p.entity_id: p for p in self._presenter.list_cache_expiration_policies()}
        self._reload_cache_entries()
        self._reload_conflicts()

    def _selected_policy_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            MessageDialog.warning(self, "Offline", "Selecciona una política primero.")
        return row_id

    def _on_new_policy(self) -> None:
        dlg = CacheExpirationPolicyCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["entity_type"]:
            MessageDialog.warning(self, "Offline", "El tipo de entidad es obligatorio.")
            return
        ok, message = self._presenter.create_cache_expiration_policy(**values)
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Offline", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_policy(self) -> None:
        policy_id = self._selected_policy_id()
        if not policy_id:
            return
        policy = self._policies_by_id.get(policy_id)
        if policy is None:
            MessageDialog.warning(self, "Offline", "La política ya no existe.")
            return
        dlg = CacheExpirationPolicyEditDialog(self, ttl_seconds=policy.ttl_seconds)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.update_cache_expiration_policy(policy_id=policy_id, **dlg.values())
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Offline", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_policy_status(self, action: str) -> None:
        policy_id = self._selected_policy_id()
        if not policy_id:
            return
        ok, message = self._presenter.change_cache_expiration_policy_status(policy_id=policy_id, action=action)
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Offline", message)
        if ok:
            self.reload(self.search.text())

    # ── Caché por estación (solo lectura, sin botones de acción) ───────────

    def _build_cache_card(self) -> None:
        self.cache_card = SectionCard(self, title="Caché por estación")
        self.cache_table = StandardTable(_CACHE_COLUMNS, self.cache_card)
        self.cache_table.setAccessibleName("Entradas de caché por estación")
        self.cache_card.add(self.cache_table)
        self.cache_empty = None
        self.layout().addWidget(self.cache_card)
        self._reload_cache_entries()

    def _reload_cache_entries(self) -> None:
        entries = self._presenter.list_offline_cache_entries()
        rows = [
            [e.entity_type, e.cached_entity_id, e.workstation_name, e.sync_state, e.cached_at]
            for e in entries
        ]
        self.cache_table.load_rows(rows, row_ids=[e.entity_id for e in entries])
        if self.cache_empty is not None:
            self.cache_empty.setParent(None)
            self.cache_empty = None
        if not rows:
            self.cache_empty = create_state_widget(ViewState.EMPTY, self.cache_card, message=_CACHE_EMPTY_MESSAGE)
            self.cache_card.add(self.cache_empty)
        self.cache_table.setVisible(bool(rows))

    # ── Conflictos de sincronización (SDLC-SYNC-002) ───────────────────────

    def _build_conflicts_card(self) -> None:
        self.conflicts_card = SectionCard(self, title="Conflictos de sincronización")
        self.conflicts_table = StandardTable(_CONFLICT_COLUMNS, self.conflicts_card)
        self.conflicts_table.setAccessibleName("Conflictos de sincronización pendientes")
        self.retry_conflict_button = create_secondary_button(self, "Reintentar")
        self.accept_remote_button = create_warning_button(self, "Aceptar lo del servidor")
        self.retry_conflict_button.clicked.connect(lambda: self._on_resolve_conflict("RETRY_LOCAL"))
        self.accept_remote_button.clicked.connect(lambda: self._on_resolve_conflict("ACCEPT_REMOTE"))
        self.conflicts_card.add(_button_row(self, self.retry_conflict_button, self.accept_remote_button))
        self.conflicts_card.add(self.conflicts_table)
        self.conflicts_empty = None
        self.layout().addWidget(self.conflicts_card)
        self._reload_conflicts()

    def _reload_conflicts(self) -> None:
        conflicts = self._presenter.list_replication_conflicts()
        rows = [[str(c.sequence_no), c.source, c.event_type, c.error, c.created_at] for c in conflicts]
        self.conflicts_table.load_rows(rows, row_ids=[c.envelope_id for c in conflicts])
        if self.conflicts_empty is not None:
            self.conflicts_empty.setParent(None)
            self.conflicts_empty = None
        if not rows:
            self.conflicts_empty = create_state_widget(
                ViewState.EMPTY, self.conflicts_card, message=_CONFLICT_EMPTY_MESSAGE)
            self.conflicts_card.add(self.conflicts_empty)
        self.conflicts_table.setVisible(bool(rows))
        self.retry_conflict_button.setEnabled(bool(rows))
        self.accept_remote_button.setEnabled(bool(rows))

    def _on_resolve_conflict(self, strategy: str) -> None:
        envelope_id = self.conflicts_table.selected_row_id()
        if not envelope_id:
            MessageDialog.warning(self, "Offline", "Selecciona un conflicto primero.")
            return
        title = ("Reintentar el envío" if strategy == "RETRY_LOCAL"
                 else "Aceptar lo del servidor: este hecho no llegará a los libros centrales")
        dialog = ResolveReplicationConflictDialog(self, title=title)
        if dialog.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.resolve_replication_conflict(
            envelope_id=envelope_id, strategy=strategy, **dialog.values())
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Offline", message)
        if ok:
            self._reload_conflicts()


__all__ = ["OfflinePage"]
