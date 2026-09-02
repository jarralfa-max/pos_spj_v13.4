"""MemberProfilePage (LOY-25, route ``loyalty.member_profile``) — search a
customer by id, show their loyalty account balance/memberships/recent
ledger, and act on it (acreditar/canjear puntos).

No `CustomerSearchBox`-style picker is wired here — that component needs a
`SearchProvider` querying Customer Master, a separate piece of wiring out
of scope for this phase (documented, not silently skipped). The field
accepts a raw ``customer_id`` (UUIDv7) directly; a nicer picker is a
follow-up, not a structural limitation of this page.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, FormField, StandardForm, StandardTable
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

_MEMBERSHIP_LABELS = {
    "ACTIVE": "Activa", "SUSPENDED": "Suspendida", "BLOCKED": "Bloqueada", "CLOSED": "Cerrada",
}


class MemberProfilePage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fidelidadMemberProfilePage")
        self._presenter = presenter
        self._current_customer_id: str | None = None
        self._current_account_id: str | None = None

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

        self._balance_label = QLabel("", self)
        self._balance_label.setObjectName("fidelidadMemberBalance")
        layout.addWidget(self._balance_label)

        layout.addWidget(QLabel("Membresías", self))
        self._memberships_table = StandardTable(
            [ColumnSpec("Programa"), ColumnSpec("Estado", "status")], self)
        layout.addWidget(self._memberships_table)

        layout.addWidget(QLabel("Movimientos recientes", self))
        self._ledger_table = StandardTable(
            [ColumnSpec("Tipo"), ColumnSpec("Monto", "numeric"), ColumnSpec("Motivo"),
             ColumnSpec("Fecha", "date")], self)
        layout.addWidget(self._ledger_table)

        layout.addWidget(QLabel("Acreditar / canjear puntos", self))
        self._points_form = StandardForm(self)
        self._points_amount_input = StandardLineEdit(self)
        self._points_form.add_field(
            "points_amount", FormField("Cantidad de puntos", self._points_amount_input,
                                       required=True))
        self._reason_input = StandardLineEdit(self)
        self._points_form.add_field(
            "reason", FormField("Motivo", self._reason_input, required=True))
        layout.addWidget(self._points_form)

        points_actions = QHBoxLayout()
        accrue_btn = create_primary_button(self, "Acreditar puntos")
        accrue_btn.clicked.connect(self._accrue_points)
        points_actions.addWidget(accrue_btn)
        redeem_btn = create_secondary_button(self, "Canjear puntos")
        redeem_btn.clicked.connect(self._redeem_points)
        points_actions.addWidget(redeem_btn)
        points_actions.addStretch(1)
        layout.addLayout(points_actions)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass  # nothing to load until a customer id is searched

    def show_customer(self, customer_id: str) -> None:
        self._customer_id_input.setText(customer_id)
        self._search()

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
            self._current_customer_id = None
            self._current_account_id = None
            self._balance_label.setText("")
            self._memberships_table.load_rows([])
            self._ledger_table.load_rows([])
            self._show_message(
                "Este cliente no tiene una cuenta de fidelidad todavía.", error=True)
            return

        self._current_customer_id = customer_id
        self._current_account_id = view.account.id
        self._balance_label.setText(f"Saldo de puntos: {view.balance}")
        self._memberships_table.load_rows(
            [[m.program_id, _MEMBERSHIP_LABELS.get(m.status.value, m.status.value)]
             for m in view.memberships],
            row_ids=[m.id for m in view.memberships])
        self._ledger_table.load_rows([
            [t.transaction_type.value, str(t.points_amount), t.reason_code or "",
             (t.created_at or "")[:10]]
            for t in view.recent_transactions
        ])
        self._show_message("", error=False)
        self._status.hide()

    def _accrue_points(self) -> None:
        self._apply_points_action(self._presenter.accrue_points, "acreditados")

    def _redeem_points(self) -> None:
        self._apply_points_action(self._presenter.redeem_points, "canjeados")

    def _apply_points_action(self, action, verb: str) -> None:
        if not self._current_account_id:
            self._show_message("Busca un cliente primero.", error=True)
            return
        errors = {}
        amount: Decimal | None = None
        try:
            amount = Decimal(self._points_amount_input.text().strip())
            if amount <= 0:
                errors["points_amount"] = "Debe ser positivo"
        except (InvalidOperation, ValueError):
            errors["points_amount"] = "Cantidad inválida"
        if not self._reason_input.text().strip():
            errors["reason"] = "El motivo es obligatorio"
        self._points_form.set_errors(errors)
        if errors:
            return
        result = action(
            loyalty_account_id=self._current_account_id, points_amount=amount,
            reason_code=self._reason_input.text().strip())
        if result.success:
            message = result.message or f"Puntos {verb}."
        else:
            message = result.message
        self._show_message(message, error=not result.success)
        if result.success:
            self._points_amount_input.clear()
            self._reason_input.clear()
            self._points_form.clear_errors()
            self._search()

    def _show_message(self, message: str, *, error: bool) -> None:
        if not message:
            self._status.hide()
            return
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
