"""Thin CASH-12 blind count UI; expected cash is absent until authorized reveal."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.quantity_input import QuantityInput
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class BlindCountPage(QWidget):
    capture_requested = pyqtSignal(str, int)
    confirm_requested = pyqtSignal()
    reveal_requested = pyqtSignal()

    def __init__(self, query_service, *, count_id: str, branch_id: str,
                 requester_user_id: str, parent=None):
        super().__init__(parent)
        self._query = query_service
        self._count_id, self._branch_id = count_id, branch_id
        self._requester_user_id = requester_user_id
        root = QVBoxLayout(self)
        confirm = create_primary_button(self, "Confirmar y bloquear")
        reveal = create_secondary_button(self, "Revelar esperado")
        confirm.clicked.connect(self.confirm_requested.emit)
        reveal.clicked.connect(self.reveal_requested.emit)
        root.addWidget(PageHeader(
            self, title="Conteo ciego",
            subtitle="Capture denominaciones sin consultar el efectivo esperado.",
            actions=[reveal, confirm]))
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
        capture.clicked.connect(self._request_capture)
        capture_row.addWidget(self._quantity)
        capture_row.addWidget(capture)
        capture_row.addStretch(1)
        root.addLayout(capture_row)
        self.refresh()

    @staticmethod
    def _money(value): return f"${value:,.2f}"

    def refresh(self, *, reveal_expected: bool = False):
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
        self._quantity.setEnabled(not dto.locked)

    def _request_capture(self):
        denomination_id = self._table.selected_row_id()
        if denomination_id:
            self.capture_requested.emit(denomination_id, int(self._quantity.value()))
