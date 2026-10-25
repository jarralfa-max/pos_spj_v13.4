"""MemberProfilePage (LOY-25, route ``loyalty.member_profile``) — search a
customer by id, show their loyalty account balance/memberships/recent
ledger, and act on it (acreditar/canjear puntos).

LOY-29: el cliente se elige con el buscador estándar de Clientes
(`CustomerSearchBox`); antes había que pegar su UUID.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import (
    ColumnSpec,
    CustomerSearchBox,
    StandardTable,
)
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.themes.tokens import Spacing

_MEMBERSHIP_LABELS = {
    "ACTIVE": "Activa", "SUSPENDED": "Suspendida", "BLOCKED": "Bloqueada", "CLOSED": "Cerrada",
}


class MemberProfilePage(StandardPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent, title="Perfil de miembro", subtitle="Cuenta, membresías, saldo y movimientos de un cliente.")
        self.setObjectName("fidelidadMemberProfilePage")
        self._presenter = presenter
        self._current_customer_id: str | None = None
        self._current_account_id: str | None = None

        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        # LOY-29: buscador estándar de Clientes (antes había que pegar el UUID).
        self._selected_customer_id: str | None = None
        self._customer_search = CustomerSearchBox(self, provider=presenter.customer_options)
        self._customer_search.selected.connect(self._on_customer_selected)
        layout.addWidget(self._customer_search)

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

        aviso = QLabel(
            "Los puntos se ganan y se gastan en el punto de venta o con una recompensa. Para "
            "corregir un saldo usa Puntos → Cuentas → «Corrección manual» (documento, motivo y "
            "otra persona que autoriza).", self)
        aviso.setWordWrap(True)
        layout.addWidget(aviso)
        layout.addStretch(1)

    def ensure_loaded(self) -> None:
        pass  # nothing to load until a customer id is searched

    def show_customer(self, customer_id: str) -> None:
        self._selected_customer_id = customer_id
        self._search()

    def _on_customer_selected(self, option) -> None:
        self._selected_customer_id = option.id
        self._customer_search.set_selected_label(option.label)
        self._search()

    def _search(self) -> None:
        customer_id = self._selected_customer_id or ""
        if not customer_id:
            self._show_message("Busca y elige un cliente.", error=True)
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
            [[view.program_names.get(m.program_id) or m.program_id, _MEMBERSHIP_LABELS.get(m.status.value, m.status.value)]
             for m in view.memberships],
            row_ids=[m.id for m in view.memberships])
        self._ledger_table.load_rows([
            [t.transaction_type.value, str(t.points_amount), t.reason_code or "",
             (t.created_at or "")[:10]]
            for t in view.recent_transactions
        ])
        self._show_message("", error=False)
        self._status.hide()

    def _show_message(self, message: str, *, error: bool) -> None:
        if not message:
            self._status.hide()
            return
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
