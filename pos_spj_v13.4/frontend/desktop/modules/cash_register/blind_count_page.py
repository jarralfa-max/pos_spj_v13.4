"""CASH-12 blind count UI; expected cash is absent until authorized reveal."""

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.quantity_input import QuantityInput
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class BlindCountPage(QWidget):
    def __init__(self, query_service, *, presenter, count_id: str | None = None,
                 branch_id: str | None = None, requester_user_id: str | None = None,
                 parent=None):
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        self._count_id, self._branch_id = count_id, branch_id
        self._requester_user_id = requester_user_id
        root = QVBoxLayout(self)
        start = create_primary_button(self, "Iniciar conteo")
        confirm = create_primary_button(self, "Confirmar y bloquear")
        reveal = create_secondary_button(self, "Revelar esperado")
        caps = presenter.capabilities()
        start.setEnabled(bool(caps.count_start))
        confirm.setEnabled(bool(caps.count_confirm))
        reveal.setEnabled(bool(caps.count_reveal_expected))
        start.clicked.connect(self._start)
        confirm.clicked.connect(self._confirm)
        reveal.clicked.connect(self._reveal)
        root.addWidget(PageHeader(
            self, title="Conteo ciego",
            subtitle="Capture denominaciones sin consultar el efectivo esperado.",
            actions=[reveal, confirm, start]))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._expected = QLabel("Esperado: oculto", self)
        self._expected.setProperty("role", "secondaryText")
        root.addWidget(self._expected)
        self._table = StandardTable([
            ColumnSpec("Denominación"), ColumnSpec("Valor", "numeric"),
            ColumnSpec("Cantidad", "numeric"), ColumnSpec("Subtotal", "numeric"),
        ], self)
        root.addWidget(self._table)
        capture_row = QHBoxLayout()
        self._quantity = QuantityInput(self, decimals=0)
        capture = create_secondary_button(self, "Guardar cantidad")
        capture.setEnabled(bool(caps.count_capture))
        capture.clicked.connect(self._request_capture)
        capture_row.addWidget(self._quantity)
        capture_row.addWidget(capture)
        capture_row.addStretch(1)
        root.addLayout(capture_row)
        self.refresh()

    @staticmethod
    def _money(value): return f"${value:,.2f}"

    def _ensure_context(self) -> bool:
        if not self._branch_id:
            self._branch_id = self._presenter.active_branch_id()
        if not self._requester_user_id:
            self._requester_user_id = self._presenter.actor_user_id()
        return bool(self._branch_id and self._requester_user_id)

    def refresh(self, *, reveal_expected: bool = False):
        if not self._count_id:
            self._expected.setText("Esperado: oculto")
            self._kpis.set_cards([
                KPIDTO("counted", "Total contado", "$0.00", 0),
                KPIDTO("status", "Estado", "Sin sesion"),
            ])
            self._table.load_rows([], row_ids=[])
            self._quantity.setEnabled(False)
            return
        self._ensure_context()
        dto = self._query.get(
            count_id=self._count_id, branch_id=self._branch_id,
            requester_user_id=self._requester_user_id,
            reveal_expected=reveal_expected)
        self._kpis.set_cards([
            KPIDTO("counted", "Total contado", self._money(dto.total_counted), dto.total_counted),
            KPIDTO("status", "Estado", "Bloqueado" if dto.locked else "En captura"),
        ])
        if dto.expected_cash is None:
            self._expected.setText("Esperado: oculto")
        else:
            self._expected.setText(
                f"Esperado: {self._money(dto.expected_cash)} · Diferencia: {self._money(dto.difference)}")
        self._table.load_rows([
            [line.display_name, self._money(line.denomination), str(line.quantity),
             self._money(line.subtotal)] for line in dto.lines],
            row_ids=[line.denomination_id for line in dto.lines])
        self._quantity.setEnabled(not dto.locked and self._presenter.capabilities().count_capture)

    def _start(self):
        try:
            result = self._presenter.start_blind_count()
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(str(exc))
            return
        self._count_id = getattr(result, "entity_id", None)
        self._branch_id = self._presenter.active_branch_id()
        self._requester_user_id = self._presenter.actor_user_id()
        self._show_result("Conteo ciego iniciado. El esperado permanece oculto.")
        self.refresh()

    def _request_capture(self):
        denomination_id = self._table.selected_row_id()
        if not denomination_id or not self._count_id:
            return
        try:
            self._presenter.capture_blind_count_denomination(
                count_id=self._count_id,
                denomination_id=denomination_id,
                quantity=int(self._quantity.value()),
            )
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(str(exc))
            return
        self.refresh()

    def _confirm(self):
        if not self._count_id:
            return
        try:
            self._presenter.confirm_blind_count(count_id=self._count_id)
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(str(exc))
            return
        self._show_result("Conteo confirmado y bloqueado.")
        self.refresh()

    def _reveal(self):
        if not self._count_id:
            return
        try:
            self.refresh(reveal_expected=True)
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(str(exc))

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", message or "No fue posible completar el conteo.")
