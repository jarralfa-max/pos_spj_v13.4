"""CardsPage (LOY-25, route ``tarjetas.cards``) — issue a card, search one
by its number, and activate/block/unblock it."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import FormField, StandardForm
from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

_STATUS_LABELS = {
    "ISSUED": "Emitida", "ACTIVE": "Activa", "BLOCKED": "Bloqueada",
    "REPLACED": "Repuesta", "CANCELLED": "Cancelada", "EXPIRED": "Vencida",
}


class CardsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("tarjetasFidelidadCardsPage")
        self._presenter = presenter
        self._current_card_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        layout.addWidget(QLabel("Emitir tarjeta", self))
        self._issue_form = StandardForm(self)
        self._customer_id_input = StandardLineEdit(self)
        self._issue_form.add_field(
            "customer_id", FormField("ID de cliente", self._customer_id_input, required=True))
        self._membership_id_input = StandardLineEdit(self)
        self._issue_form.add_field(
            "membership_id", FormField("ID de membresía", self._membership_id_input,
                                       required=True))
        layout.addWidget(self._issue_form)
        issue_btn = create_primary_button(self, "Emitir tarjeta")
        issue_btn.clicked.connect(self._issue)
        layout.addWidget(issue_btn)

        layout.addWidget(QLabel("Buscar tarjeta por número", self))
        search_row = QHBoxLayout()
        self._card_number_input = StandardLineEdit(self)
        self._card_number_input.setPlaceholderText("LC-00000001")
        search_row.addWidget(self._card_number_input, stretch=1)
        search_btn = create_secondary_button(self, "Buscar")
        search_btn.clicked.connect(self._search)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        self._card_details = QLabel("", self)
        self._card_details.setWordWrap(True)
        layout.addWidget(self._card_details)

        card_actions = QHBoxLayout()
        activate_btn = create_secondary_button(self, "Activar")
        activate_btn.clicked.connect(self._activate)
        card_actions.addWidget(activate_btn)
        self._block_reason_input = StandardLineEdit(self)
        self._block_reason_input.setPlaceholderText("Motivo de bloqueo")
        card_actions.addWidget(self._block_reason_input, stretch=1)
        block_btn = create_danger_button(self, "Bloquear")
        block_btn.clicked.connect(self._block)
        card_actions.addWidget(block_btn)
        unblock_btn = create_secondary_button(self, "Desbloquear")
        unblock_btn.clicked.connect(self._unblock)
        card_actions.addWidget(unblock_btn)
        layout.addLayout(card_actions)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass

    def _issue(self) -> None:
        errors = {}
        if not self._customer_id_input.text().strip():
            errors["customer_id"] = "Obligatorio"
        if not self._membership_id_input.text().strip():
            errors["membership_id"] = "Obligatorio"
        self._issue_form.set_errors(errors)
        if errors:
            return
        result = self._presenter.issue_card(
            customer_id=self._customer_id_input.text().strip(),
            membership_id=self._membership_id_input.text().strip())
        if result.success:
            card_number = result.data.get("card_number", "")
            self._show_message(f"{result.message}: {card_number}", error=False)
            self._card_number_input.setText(card_number)
            self._search()
        else:
            self._show_message(result.message, error=True)

    def _search(self) -> None:
        card_number = self._card_number_input.text().strip()
        if not card_number:
            self._show_message("Ingresa un número de tarjeta.", error=True)
            return
        card = self._presenter.find_card_by_number(card_number)
        if card is None:
            self._current_card_id = None
            self._card_details.setText("No se encontró ninguna tarjeta con ese número.")
            return
        self._current_card_id = card.id
        status_label = _STATUS_LABELS.get(card.status.value, card.status.value)
        self._card_details.setText(
            f"Tarjeta {card.card_number} — {card.card_type.value} — Estado: {status_label}\n"
            f"Cliente: {card.customer_id}")
        self._show_message("", error=False)

    def _activate(self) -> None:
        if not self._current_card_id:
            self._show_message("Busca una tarjeta primero.", error=True)
            return
        result = self._presenter.activate_card(self._current_card_id)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self._search()

    def _block(self) -> None:
        if not self._current_card_id:
            self._show_message("Busca una tarjeta primero.", error=True)
            return
        reason = self._block_reason_input.text().strip()
        if not reason:
            self._show_message("El bloqueo requiere un motivo.", error=True)
            return
        result = self._presenter.block_card(card_id=self._current_card_id, reason=reason)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self._block_reason_input.clear()
            self._search()

    def _unblock(self) -> None:
        if not self._current_card_id:
            self._show_message("Busca una tarjeta primero.", error=True)
            return
        result = self._presenter.unblock_card(self._current_card_id)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self._search()

    def _show_message(self, message: str, *, error: bool) -> None:
        if not message:
            self._status.hide()
            return
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
