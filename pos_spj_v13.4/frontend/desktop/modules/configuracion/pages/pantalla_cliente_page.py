"""Pantalla del cliente page — SET-18 cutover, real CRUD for the
advertising cards. Keeps the existing read-only Displays list
(`config_pantalla_cliente` page, SET-17, untouched — this page's base
`reload()` already renders it) and adds 4 `SectionCard`s: Contenido,
Campañas (7-action approval lifecycle — same button row
`documentos_page.py` already uses for template versions), Slots
publicitarios, and Asignaciones (+ a per-row "Ver métricas" action).
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    AdvertisingSlotCreateDialog,
    AdvertisingSlotEditDialog,
    CampaignPlacementAssignDialog,
    ContentCampaignCreateDialog,
    ContentCampaignEditDialog,
    ContentCreateDialog,
    ContentEditDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_CONTENT_COLUMNS = [
    ColumnSpec("Título"), ColumnSpec("Tipo"), ColumnSpec("Duración (s)", "numeric"),
    ColumnSpec("Activo", "status"),
]
_CAMPAIGN_COLUMNS = [
    ColumnSpec("Nombre"), ColumnSpec("Contenido"), ColumnSpec("Estado", "status"), ColumnSpec("Inicio"),
    ColumnSpec("Fin"),
]
_SLOT_COLUMNS = [
    ColumnSpec("Código"), ColumnSpec("Modo"), ColumnSpec("Orden", "numeric"), ColumnSpec("Activo", "status"),
]
_PLACEMENT_COLUMNS = [
    ColumnSpec("Campaña"), ColumnSpec("Slot"), ColumnSpec("Activo", "status"), ColumnSpec("Asignado"),
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


class PantallaClientePage(ConfiguracionWorkspacePage):
    page_id = "config_pantalla_cliente"
    title = "Pantalla del cliente"
    subtitle = "Displays, contenido y publicidad."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._campaigns_by_id: dict = {}
        self._slots_by_id: dict = {}
        self._placements_by_id: dict = {}

        self._build_content_card()
        self._build_campaigns_card()
        self._build_slots_card()
        self._build_placements_card()

        self._reload_content()
        self._reload_campaigns()
        self._reload_slots()
        self._reload_placements()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        self._reload_content()
        self._reload_campaigns()
        self._reload_slots()
        self._reload_placements()

    # ── Contenido ────────────────────────────────────────────────────────

    def _build_content_card(self) -> None:
        self.content_card = SectionCard(self, title="Contenido")
        self.content_table = StandardTable(_CONTENT_COLUMNS, self.content_card)
        self.content_table.setAccessibleName("Contenido de publicidad")
        self.content_card.add(self.content_table)
        self.content_empty = None

        self.new_content_button = create_primary_button(self.content_card, "Nuevo contenido")
        self.edit_content_button = create_secondary_button(self.content_card, "Editar contenido")
        self.activate_content_button = create_secondary_button(self.content_card, "Activar")
        self.deactivate_content_button = create_warning_button(self.content_card, "Desactivar")
        self.content_card.add(_button_row(
            self.content_card, self.new_content_button, self.edit_content_button,
            self.activate_content_button, self.deactivate_content_button,
        ))
        self.layout().addWidget(self.content_card)

        self.new_content_button.clicked.connect(self._on_new_content)
        self.edit_content_button.clicked.connect(self._on_edit_content)
        self.activate_content_button.clicked.connect(lambda: self._on_change_content_status("ACTIVATE"))
        self.deactivate_content_button.clicked.connect(lambda: self._on_change_content_status("DEACTIVATE"))

    def _reload_content(self) -> None:
        items = self._presenter.list_display_content()
        rows = [[c.title, c.content_type, str(c.duration_seconds), "Sí" if c.active else "No"] for c in items]
        self.content_table.load_rows(rows, row_ids=[c.entity_id for c in items])
        if self.content_empty is not None:
            self.content_empty.setParent(None)
            self.content_empty = None
        if not rows:
            self.content_empty = create_state_widget(
                ViewState.EMPTY, self.content_card, message="No hay contenido todavía.")
            self.content_card.add(self.content_empty)
        self.content_table.setVisible(bool(rows))

    def _selected_content_id(self) -> str | None:
        row_id = self.content_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Pantalla del cliente", "Selecciona un contenido primero.")
        return row_id

    def _on_new_content(self) -> None:
        dlg = ContentCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["title"] or not values["content_type"] or not values["body"]:
            QMessageBox.warning(self, "Pantalla del cliente", "Título, tipo y contenido son obligatorios.")
            return
        ok, message = self._presenter.create_display_content(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_content()

    def _on_edit_content(self) -> None:
        content_id = self._selected_content_id()
        if not content_id:
            return
        content = self._presenter.get_display_content(content_id)
        if content is None:
            QMessageBox.warning(self, "Pantalla del cliente", "El contenido ya no existe.")
            return
        dlg = ContentEditDialog(
            self, title=content.title, body=content.body, duration_seconds=content.duration_seconds)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["title"] or not values["body"]:
            QMessageBox.warning(self, "Pantalla del cliente", "Título y contenido son obligatorios.")
            return
        ok, message = self._presenter.update_display_content(content_id=content_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_content()

    def _on_change_content_status(self, action: str) -> None:
        content_id = self._selected_content_id()
        if not content_id:
            return
        ok, message = self._presenter.change_display_content_status(content_id=content_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_content()

    # ── Campañas ─────────────────────────────────────────────────────────

    def _build_campaigns_card(self) -> None:
        self.campaigns_card = SectionCard(self, title="Campañas")
        self.campaigns_table = StandardTable(_CAMPAIGN_COLUMNS, self.campaigns_card)
        self.campaigns_table.setAccessibleName("Campañas de contenido")
        self.campaigns_card.add(self.campaigns_table)
        self.campaigns_empty = None

        self.new_campaign_button = create_primary_button(self.campaigns_card, "Nueva campaña")
        self.edit_campaign_button = create_secondary_button(self.campaigns_card, "Editar vigencia")
        self.submit_campaign_button = create_secondary_button(self.campaigns_card, "Enviar a aprobación")
        self.approve_campaign_button = create_primary_button(self.campaigns_card, "Aprobar")
        self.reject_campaign_button = create_danger_button(self.campaigns_card, "Rechazar")
        self.activate_campaign_button = create_primary_button(self.campaigns_card, "Activar")
        self.deactivate_campaign_button = create_warning_button(self.campaigns_card, "Desactivar")
        self.expire_campaign_button = create_warning_button(self.campaigns_card, "Expirar")
        self.archive_campaign_button = create_secondary_button(self.campaigns_card, "Archivar")
        self.campaigns_card.add(_button_row(
            self.campaigns_card, self.new_campaign_button, self.edit_campaign_button,
            self.submit_campaign_button, self.approve_campaign_button, self.reject_campaign_button,
            self.activate_campaign_button, self.deactivate_campaign_button, self.expire_campaign_button,
            self.archive_campaign_button,
        ))
        self.layout().addWidget(self.campaigns_card)

        self.new_campaign_button.clicked.connect(self._on_new_campaign)
        self.edit_campaign_button.clicked.connect(self._on_edit_campaign)
        self.submit_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("SUBMIT_FOR_APPROVAL"))
        self.approve_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("APPROVE"))
        self.reject_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("REJECT"))
        self.activate_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("ACTIVATE"))
        self.deactivate_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("DEACTIVATE"))
        self.expire_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("EXPIRE"))
        self.archive_campaign_button.clicked.connect(lambda: self._on_change_campaign_status("ARCHIVE"))

    def _reload_campaigns(self) -> None:
        campaigns = self._presenter.list_content_campaigns()
        self._campaigns_by_id = {c.entity_id: c for c in campaigns}
        rows = [
            [c.name, c.content_title, c.status, c.starts_at or "—", c.ends_at or "—"] for c in campaigns
        ]
        self.campaigns_table.load_rows(rows, row_ids=[c.entity_id for c in campaigns])
        if self.campaigns_empty is not None:
            self.campaigns_empty.setParent(None)
            self.campaigns_empty = None
        if not rows:
            self.campaigns_empty = create_state_widget(
                ViewState.EMPTY, self.campaigns_card, message="No hay campañas todavía.")
            self.campaigns_card.add(self.campaigns_empty)
        self.campaigns_table.setVisible(bool(rows))

    def _selected_campaign_id(self) -> str | None:
        row_id = self.campaigns_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Pantalla del cliente", "Selecciona una campaña primero.")
        return row_id

    def _on_new_campaign(self) -> None:
        dlg = ContentCampaignCreateDialog(self, content_options=self._presenter.list_display_content())
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"] or not values["content_id"]:
            QMessageBox.warning(self, "Pantalla del cliente", "Nombre y contenido son obligatorios.")
            return
        ok, message = self._presenter.create_content_campaign(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_campaigns()

    def _on_edit_campaign(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            return
        campaign = self._campaigns_by_id.get(campaign_id)
        dlg = ContentCampaignEditDialog(
            self, starts_at=campaign.starts_at if campaign else None,
            ends_at=campaign.ends_at if campaign else None,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.update_content_campaign(campaign_id=campaign_id, **dlg.values())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_campaigns()

    def _on_change_campaign_status(self, action: str) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            return
        reason = ""
        if action == "REJECT":
            reason, ok_pressed = self._ask_reason()
            if not ok_pressed:
                return
        ok, message = self._presenter.change_content_campaign_status(
            campaign_id=campaign_id, action=action, reason=reason)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_campaigns()

    def _ask_reason(self) -> tuple[str, bool]:
        from PyQt5.QtWidgets import QInputDialog
        reason, ok_pressed = QInputDialog.getText(self, "Rechazar campaña", "Motivo:")
        return reason.strip(), ok_pressed and bool(reason.strip())

    # ── Slots publicitarios ──────────────────────────────────────────────

    def _build_slots_card(self) -> None:
        self.slots_card = SectionCard(self, title="Slots publicitarios")
        self.slots_table = StandardTable(_SLOT_COLUMNS, self.slots_card)
        self.slots_table.setAccessibleName("Slots publicitarios")
        self.slots_card.add(self.slots_table)
        self.slots_empty = None

        self.new_slot_button = create_primary_button(self.slots_card, "Nuevo slot")
        self.edit_slot_button = create_secondary_button(self.slots_card, "Editar orden")
        self.activate_slot_button = create_secondary_button(self.slots_card, "Activar")
        self.deactivate_slot_button = create_warning_button(self.slots_card, "Desactivar")
        self.slots_card.add(_button_row(
            self.slots_card, self.new_slot_button, self.edit_slot_button, self.activate_slot_button,
            self.deactivate_slot_button,
        ))
        self.layout().addWidget(self.slots_card)

        self.new_slot_button.clicked.connect(self._on_new_slot)
        self.edit_slot_button.clicked.connect(self._on_edit_slot)
        self.activate_slot_button.clicked.connect(lambda: self._on_change_slot_status("ACTIVATE"))
        self.deactivate_slot_button.clicked.connect(lambda: self._on_change_slot_status("DEACTIVATE"))

    def _reload_slots(self) -> None:
        slots = self._presenter.list_advertising_slots()
        self._slots_by_id = {s.entity_id: s for s in slots}
        rows = [[s.code, s.mode, str(s.display_order), "Sí" if s.active else "No"] for s in slots]
        self.slots_table.load_rows(rows, row_ids=[s.entity_id for s in slots])
        if self.slots_empty is not None:
            self.slots_empty.setParent(None)
            self.slots_empty = None
        if not rows:
            self.slots_empty = create_state_widget(
                ViewState.EMPTY, self.slots_card, message="No hay slots publicitarios todavía.")
            self.slots_card.add(self.slots_empty)
        self.slots_table.setVisible(bool(rows))

    def _selected_slot_id(self) -> str | None:
        row_id = self.slots_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Pantalla del cliente", "Selecciona un slot primero.")
        return row_id

    def _on_new_slot(self) -> None:
        dlg = AdvertisingSlotCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["mode"]:
            QMessageBox.warning(self, "Pantalla del cliente", "Código y modo son obligatorios.")
            return
        ok, message = self._presenter.create_advertising_slot(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_slots()

    def _on_edit_slot(self) -> None:
        slot_id = self._selected_slot_id()
        if not slot_id:
            return
        slot = self._slots_by_id.get(slot_id)
        if slot is None:
            QMessageBox.warning(self, "Pantalla del cliente", "El slot ya no existe.")
            return
        dlg = AdvertisingSlotEditDialog(self, display_order=slot.display_order)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.update_advertising_slot(slot_id=slot_id, **dlg.values())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_slots()

    def _on_change_slot_status(self, action: str) -> None:
        slot_id = self._selected_slot_id()
        if not slot_id:
            return
        ok, message = self._presenter.change_advertising_slot_status(slot_id=slot_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_slots()

    # ── Asignaciones ─────────────────────────────────────────────────────

    def _build_placements_card(self) -> None:
        self.placements_card = SectionCard(self, title="Asignaciones")
        self.placements_table = StandardTable(_PLACEMENT_COLUMNS, self.placements_card)
        self.placements_table.setAccessibleName("Asignaciones de campañas a slots")
        self.placements_card.add(self.placements_table)
        self.placements_empty = None

        self.new_placement_button = create_primary_button(self.placements_card, "Asignar")
        self.unassign_placement_button = create_warning_button(self.placements_card, "Liberar")
        self.metrics_placement_button = create_secondary_button(self.placements_card, "Ver métricas")
        self.placements_card.add(_button_row(
            self.placements_card, self.new_placement_button, self.unassign_placement_button,
            self.metrics_placement_button,
        ))
        self.layout().addWidget(self.placements_card)

        self.new_placement_button.clicked.connect(self._on_new_placement)
        self.unassign_placement_button.clicked.connect(self._on_unassign_placement)
        self.metrics_placement_button.clicked.connect(self._on_view_metrics)

    def _reload_placements(self) -> None:
        placements = self._presenter.list_campaign_placements()
        self._placements_by_id = {p.entity_id: p for p in placements}
        rows = [
            [p.campaign_name, p.slot_code, "Sí" if p.active else "No", p.assigned_at]
            for p in placements
        ]
        self.placements_table.load_rows(rows, row_ids=[p.entity_id for p in placements])
        if self.placements_empty is not None:
            self.placements_empty.setParent(None)
            self.placements_empty = None
        if not rows:
            self.placements_empty = create_state_widget(
                ViewState.EMPTY, self.placements_card, message="No hay asignaciones todavía.")
            self.placements_card.add(self.placements_empty)
        self.placements_table.setVisible(bool(rows))

    def _selected_placement_id(self) -> str | None:
        row_id = self.placements_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Pantalla del cliente", "Selecciona una asignación primero.")
        return row_id

    def _on_new_placement(self) -> None:
        dlg = CampaignPlacementAssignDialog(
            self, campaign_options=self._presenter.list_content_campaigns(),
            slot_options=self._presenter.list_advertising_slots(),
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["campaign_id"] or not values["slot_id"]:
            QMessageBox.warning(self, "Pantalla del cliente", "Campaña y slot son obligatorios.")
            return
        ok, message = self._presenter.assign_campaign_placement(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_placements()

    def _on_unassign_placement(self) -> None:
        placement_id = self._selected_placement_id()
        if not placement_id:
            return
        ok, message = self._presenter.unassign_campaign_placement(placement_id=placement_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Pantalla del cliente", message)
        if ok:
            self._reload_placements()

    def _on_view_metrics(self) -> None:
        placement_id = self._selected_placement_id()
        if not placement_id:
            return
        summary = self._presenter.get_impression_summary(placement_id)
        QMessageBox.information(self, "Métricas de la asignación", summary)


__all__ = ["PantallaClientePage"]
