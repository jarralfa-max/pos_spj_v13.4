"""CASH-16 value handovers page."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import (
    CashHandoverDenominationDialog,
    DisputeCashHandoverDialog,
)
from frontend.desktop.modules.cash_register.presentation import display_code, status_label, user_facing_error


class CashHandoversPage(QWidget):
    def __init__(self, query_service, *, presenter, parent=None):
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        self._rows_by_id = {}
        root = QVBoxLayout(self)
        deliver = create_secondary_button(self, "Entregar")
        receive = create_secondary_button(self, "Recibir")
        dispute = create_secondary_button(self, "Disputar")
        caps = presenter.capabilities()
        deliver.setEnabled(bool(caps.handover_deliver))
        receive.setEnabled(bool(caps.handover_receive))
        dispute.setEnabled(bool(caps.handover_dispute))
        deliver.clicked.connect(self._deliver)
        receive.clicked.connect(self._receive)
        dispute.clicked.connect(self._dispute)
        root.addWidget(PageHeader(
            self,
            title="Entrega de valores",
            subtitle="Preparacion, doble confirmacion, recepcion y disputas.",
            actions=[dispute, receive, deliver],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Preparada"), ColumnSpec("Estado", "status"),
            ColumnSpec("Monto", "numeric"), ColumnSpec("Preparó"),
            ColumnSpec("Entregó"), ColumnSpec("Recibió"), ColumnSpec("Disputa"),
        ], self)
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value):
        return f"${value:,.2f}"

    def refresh(self):
        rows = self._query.list_for_branch(self._presenter.active_branch_id())
        self._rows_by_id = {row.id: row for row in rows}
        pending = sum(1 for row in rows if row.status in {"PREPARED", "DELIVERED"})
        disputed = sum(1 for row in rows if row.status == "DISPUTED")
        self._kpis.set_cards([
            KPIDTO("pending", "Pendientes", str(pending), pending),
            KPIDTO("disputed", "Disputadas", str(disputed), disputed),
            KPIDTO("total", "Entregas", str(len(rows)), len(rows)),
        ])
        self._table.load_rows([
            [
                row.prepared_at, status_label(row.status), self._money(row.amount),
                display_code("USR", row.prepared_by),
                display_code("USR", row.delivered_by) if row.delivered_by else "-",
                display_code("USR", row.received_by) if row.received_by else "-",
                row.dispute_reason or "-",
            ]
            for row in rows
        ], row_ids=[row.id for row in rows])

    def _selected_handover_id(self) -> str | None:
        return self._table.selected_row_id()

    def _selected_handover(self):
        handover_id = self._selected_handover_id()
        return self._rows_by_id.get(handover_id or "")

    def _capture_denominations(self, title: str, handover) -> dict[str, int] | None:
        denominations = tuple(self._presenter.denomination_options())
        if not denominations:
            self._show_error("No hay denominaciones activas configuradas.")
            return None
        dialog = CashHandoverDenominationDialog(
            self,
            title=title,
            handover=handover,
            denominations=denominations,
        )
        if dialog.exec_() != dialog.Accepted:
            return None
        return dialog.result_value().quantities

    def _deliver(self) -> None:
        handover_id = self._selected_handover_id()
        if not handover_id:
            return
        handover = self._selected_handover()
        if handover is None:
            self._show_error("Selecciona una entrega vigente.")
            return
        denominations = self._capture_denominations("Confirmar entrega", handover)
        if denominations is None:
            return
        try:
            result = self._presenter.deliver_cash_handover(
                handover_id=handover_id, denominations=denominations)
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", "Entrega confirmada"))
        self.refresh()

    def _receive(self) -> None:
        handover_id = self._selected_handover_id()
        if not handover_id:
            return
        handover = self._selected_handover()
        if handover is None:
            self._show_error("Selecciona una entrega vigente.")
            return
        denominations = self._capture_denominations("Confirmar recepcion", handover)
        if denominations is None:
            return
        try:
            result = self._presenter.receive_cash_handover(
                handover_id=handover_id, denominations=denominations)
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", "Recepcion registrada"))
        self.refresh()

    def _dispute(self) -> None:
        handover_id = self._selected_handover_id()
        if not handover_id:
            return
        handover = self._selected_handover()
        if handover is None:
            self._show_error("Selecciona una entrega vigente.")
            return
        dialog = DisputeCashHandoverDialog(self, handover=handover)
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            result = self._presenter.dispute_cash_handover(
                handover_id=handover_id,
                reason=dialog.result_value().reason,
            )
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", "Entrega disputada"))
        self.refresh()

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message or "No fue posible completar la entrega."))
