"""RewardsPage (LOY-25, route ``loyalty.rewards``) — search a member,
list the rewards available to their programs, and redeem one.

Selecting a reward AND a membership row is required before "Canjear" —
a reward belongs to one program, and only a membership in that SAME
program can redeem it (`RequestRewardRedemptionUseCase`'s own domain rule);
this page lets the domain layer be the one to reject a mismatch rather than
trying to pre-filter memberships by program itself.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, StandardTable
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

_MEMBERSHIP_LABELS = {
    "ACTIVE": "Activa", "SUSPENDED": "Suspendida", "BLOCKED": "Bloqueada", "CLOSED": "Cerrada",
}


class RewardsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fidelidadRewardsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        search_row = QHBoxLayout()
        self._customer_id_input = StandardLineEdit(self)
        self._customer_id_input.setPlaceholderText("ID de cliente (UUIDv7)")
        search_row.addWidget(self._customer_id_input, stretch=1)
        search_btn = create_secondary_button(self, "Buscar")
        search_btn.clicked.connect(self._search)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        layout.addWidget(QLabel("Membresías del cliente", self))
        self._memberships_table = StandardTable(
            [ColumnSpec("Programa"), ColumnSpec("Estado", "status")], self)
        layout.addWidget(self._memberships_table)

        layout.addWidget(QLabel("Recompensas disponibles", self))
        self._rewards_table = StandardTable(
            [ColumnSpec("Código"), ColumnSpec("Nombre"), ColumnSpec("Costo en puntos", "numeric")],
            self)
        layout.addWidget(self._rewards_table)

        redeem_btn = create_primary_button(self, "Canjear recompensa seleccionada")
        redeem_btn.clicked.connect(self._redeem)
        layout.addWidget(redeem_btn)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass

    def _search(self) -> None:
        customer_id = self._customer_id_input.text().strip()
        if not customer_id:
            self._show_message("Ingresa un ID de cliente.", error=True)
            return
        try:
            view = self._presenter.member_profile(customer_id)
        except Exception as exc:
            self._show_message(f"No fue posible consultar el perfil: {exc}", error=True)
            return
        if not view.found:
            self._memberships_table.load_rows([])
            self._rewards_table.load_rows([])
            self._show_message(
                "Este cliente no tiene una cuenta de fidelidad todavía.", error=True)
            return
        self._memberships_table.load_rows(
            [[m.program_id, _MEMBERSHIP_LABELS.get(m.status.value, m.status.value)]
             for m in view.memberships],
            row_ids=[m.id for m in view.memberships])
        self._rewards_table.load_rows(
            [[r.code, r.name, str(r.points_cost)] for r in view.available_rewards],
            row_ids=[r.id for r in view.available_rewards])
        self._show_message("", error=False)

    def _redeem(self) -> None:
        reward_id = self._rewards_table.selected_row_id()
        membership_id = self._memberships_table.selected_row_id()
        if not reward_id or not membership_id:
            self._show_message(
                "Selecciona una membresía y una recompensa para canjear.", error=True)
            return
        result = self._presenter.redeem_reward(reward_id=reward_id, membership_id=membership_id)
        message = (result.message or "Recompensa canjeada.") if result.success else result.message
        self._show_message(message, error=not result.success)

    def _show_message(self, message: str, *, error: bool) -> None:
        if not message:
            self._status.hide()
            return
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
