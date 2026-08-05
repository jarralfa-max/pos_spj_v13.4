"""Thin CASH-8 ledger page; commands are emitted to its presenter/controller."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class CashLedgerPage(QWidget):
    movement_requested = pyqtSignal(str)
    reversal_requested = pyqtSignal(str)

    def __init__(self, query_service, *, shift_id: str, parent=None):
        super().__init__(parent)
        self._query, self._shift_id = query_service, shift_id
        root = QVBoxLayout(self)
        income = create_primary_button(self, "Registrar ingreso")
        withdrawal = create_secondary_button(self, "Registrar retiro")
        safe_drop = create_secondary_button(self, "Retiro a bóveda")
        reverse = create_secondary_button(self, "Reversar")
        income.clicked.connect(lambda: self.movement_requested.emit("MANUAL_INCOME"))
        withdrawal.clicked.connect(lambda: self.movement_requested.emit("MANUAL_WITHDRAWAL"))
        safe_drop.clicked.connect(lambda: self.movement_requested.emit("SAFE_DROP"))
        reverse.clicked.connect(self._request_reversal)
        root.addWidget(PageHeader(
            self, title="Ledger de caja",
            subtitle="Movimientos inmutables y saldo reconstruible del turno.",
            actions=[reverse, safe_drop, withdrawal, income]))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Tipo"), ColumnSpec("Concepto"),
            ColumnSpec("Dirección", "status"), ColumnSpec("Monto", "numeric"),
            ColumnSpec("Saldo", "numeric"), ColumnSpec("Reverso de"),
        ], self)
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value):
        return f"${value:,.2f}"

    def refresh(self):
        projection = self._query.projection(self._shift_id)
        self._kpis.set_cards([
            KPIDTO("balance", "Saldo", self._money(projection.balance), projection.balance),
            KPIDTO("inflows", "Entradas", self._money(projection.inflows), projection.inflows),
            KPIDTO("outflows", "Salidas", self._money(projection.outflows), projection.outflows),
            KPIDTO("count", "Movimientos", str(projection.movement_count), projection.movement_count),
        ])
        self._table.load_rows([
            [row.recorded_at, row.movement_type, row.concept, row.direction,
             self._money(row.amount), self._money(row.balance), row.reversal_of_id or "—"]
            for row in projection.rows], row_ids=[row.id for row in projection.rows])

    def _request_reversal(self):
        entry_id = self._table.selected_row_id()
        if entry_id:
            self.reversal_requested.emit(entry_id)
