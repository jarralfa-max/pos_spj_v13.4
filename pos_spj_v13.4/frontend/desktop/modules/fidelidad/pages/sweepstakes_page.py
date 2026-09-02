"""SweepstakesPage (LOY-25, route ``sweepstakes.campaigns``) — campaign
lifecycle (crear/aprobar/activar), premios, y otorgamiento manual de
derechos + emisión de boleto para la campaña seleccionada.

§28's own rule (boleto nunca sin derecho previo, LOY-15) is enforced by the
BACKEND, not re-checked here — this page just calls
``grant_sweepstakes_entry`` then ``issue_sweepstakes_ticket`` with the
entry id the first call returned, the same two-step sequence a real
operator would follow.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, FormField, StandardForm, StandardTable
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

_STATUS_LABELS = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente de aprobación", "APPROVED": "Aprobada",
    "ACTIVE": "Activa", "PAUSED": "Pausada", "DRAWN": "Sorteada", "CLOSED": "Cerrada",
    "CANCELLED": "Cancelada",
}


class SweepstakesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fidelidadSweepstakesPage")
        self._presenter = presenter
        self._loaded = False
        self._last_entry_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        layout.addWidget(QLabel("Campañas de sorteo", self))
        self._table = StandardTable(
            [ColumnSpec("Código"), ColumnSpec("Nombre"), ColumnSpec("Estado", "status")], self)
        layout.addWidget(self._table)

        lifecycle_actions = QHBoxLayout()
        approve_btn = create_secondary_button(self, "Aprobar seleccionada")
        approve_btn.clicked.connect(self._approve_selected)
        lifecycle_actions.addWidget(approve_btn)
        activate_btn = create_secondary_button(self, "Activar seleccionada")
        activate_btn.clicked.connect(self._activate_selected)
        lifecycle_actions.addWidget(activate_btn)
        lifecycle_actions.addStretch(1)
        layout.addLayout(lifecycle_actions)

        layout.addWidget(QLabel("Crear campaña", self))
        self._create_form = StandardForm(self)
        self._code_input = StandardLineEdit(self)
        self._create_form.add_field("code", FormField("Código", self._code_input, required=True))
        self._name_input = StandardLineEdit(self)
        self._create_form.add_field("name", FormField("Nombre", self._name_input, required=True))
        layout.addWidget(self._create_form)
        create_btn = create_primary_button(self, "Crear campaña")
        create_btn.clicked.connect(self._create_campaign)
        layout.addWidget(create_btn)

        layout.addWidget(QLabel("Agregar premio a la campaña seleccionada", self))
        self._prize_form = StandardForm(self)
        self._prize_name_input = StandardLineEdit(self)
        self._prize_form.add_field(
            "prize_name", FormField("Nombre del premio", self._prize_name_input, required=True))
        layout.addWidget(self._prize_form)
        add_prize_btn = create_secondary_button(self, "Agregar premio")
        add_prize_btn.clicked.connect(self._add_prize)
        layout.addWidget(add_prize_btn)

        layout.addWidget(QLabel("Otorgar derecho y emitir boleto", self))
        self._entry_form = StandardForm(self)
        self._entry_customer_id_input = StandardLineEdit(self)
        self._entry_form.add_field(
            "customer_id", FormField("ID de cliente", self._entry_customer_id_input,
                                     required=True))
        layout.addWidget(self._entry_form)
        entry_actions = QHBoxLayout()
        grant_btn = create_secondary_button(self, "Otorgar derecho")
        grant_btn.clicked.connect(self._grant_entry)
        entry_actions.addWidget(grant_btn)
        ticket_btn = create_primary_button(self, "Emitir boleto del último derecho")
        ticket_btn.clicked.connect(self._issue_ticket)
        entry_actions.addWidget(ticket_btn)
        entry_actions.addStretch(1)
        layout.addLayout(entry_actions)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            campaigns = self._presenter.list_sweepstakes_campaigns()
            self._table.load_rows(
                [[c.code, c.name, _STATUS_LABELS.get(c.status.value, c.status.value)]
                 for c in campaigns],
                row_ids=[c.id for c in campaigns])
            self._loaded = True
            self._status.hide()
        except Exception as exc:
            self._show_message(f"No fue posible cargar las campañas: {exc}", error=True)

    def _selected_campaign_id(self) -> str | None:
        return self._table.selected_row_id()

    def _approve_selected(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            self._show_message("Selecciona una campaña.", error=True)
            return
        result = self._presenter.approve_sweepstakes_campaign(campaign_id)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self.reload()

    def _activate_selected(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            self._show_message("Selecciona una campaña.", error=True)
            return
        result = self._presenter.activate_sweepstakes_campaign(campaign_id)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self.reload()

    def _create_campaign(self) -> None:
        errors = {}
        if not self._code_input.text().strip():
            errors["code"] = "El código es obligatorio"
        if not self._name_input.text().strip():
            errors["name"] = "El nombre es obligatorio"
        self._create_form.set_errors(errors)
        if errors:
            return
        result = self._presenter.create_sweepstakes_campaign(
            code=self._code_input.text().strip(), name=self._name_input.text().strip())
        self._show_message(result.message, error=not result.success)
        if result.success:
            self._code_input.clear()
            self._name_input.clear()
            self._create_form.clear_errors()
            self.reload()

    def _add_prize(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            self._show_message("Selecciona una campaña.", error=True)
            return
        errors = {}
        if not self._prize_name_input.text().strip():
            errors["prize_name"] = "El nombre del premio es obligatorio"
        self._prize_form.set_errors(errors)
        if errors:
            return
        result = self._presenter.add_sweepstakes_prize(
            campaign_id=campaign_id, name=self._prize_name_input.text().strip())
        self._show_message(result.message, error=not result.success)
        if result.success:
            self._prize_name_input.clear()
            self._prize_form.clear_errors()

    def _grant_entry(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            self._show_message("Selecciona una campaña.", error=True)
            return
        errors = {}
        if not self._entry_customer_id_input.text().strip():
            errors["customer_id"] = "El ID de cliente es obligatorio"
        self._entry_form.set_errors(errors)
        if errors:
            return
        result = self._presenter.grant_sweepstakes_entry(
            campaign_id=campaign_id, customer_id=self._entry_customer_id_input.text().strip())
        if result.success:
            self._last_entry_id = result.entity_id
        self._show_message(result.message, error=not result.success)

    def _issue_ticket(self) -> None:
        campaign_id = self._selected_campaign_id()
        if not campaign_id:
            self._show_message("Selecciona una campaña.", error=True)
            return
        if not self._last_entry_id:
            self._show_message("Otorga un derecho primero.", error=True)
            return
        result = self._presenter.issue_sweepstakes_ticket(
            campaign_id=campaign_id, entry_id=self._last_entry_id)
        if result.success:
            ticket_number = result.data.get("ticket_number", "")
            self._show_message(f"Boleto emitido: {ticket_number}", error=False)
        else:
            self._show_message(result.message, error=True)

    def _show_message(self, message: str, *, error: bool) -> None:
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
