"""CASH-17 refund execution page."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_primary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.modules.cash_register.cash_register_dialogs import CashRefundDialog


class CashRefundsPage(QWidget):
    def __init__(self, *, presenter, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)
        execute = create_primary_button(self, "Ejecutar reembolso")
        execute.setEnabled(bool(presenter.capabilities().refund_execute))
        execute.clicked.connect(self._execute_refund)
        root.addWidget(PageHeader(
            self,
            title="Reembolsos",
            subtitle="Ejecucion monetaria autorizada por Ventas; Caja no decide la devolucion comercial.",
            actions=[execute],
        ))
        self._kpis = KPIBar(self)
        self._kpis.set_cards([
            KPIDTO("boundary", "Frontera", "Ventas autoriza"),
            KPIDTO("cash", "Efectivo", "Ledger si aplica"),
            KPIDTO("finance", "Finanzas", "Evento operativo"),
        ])
        root.addWidget(self._kpis)
        root.addWidget(create_state_widget(
            ViewState.READY,
            self,
            message="Captura el contrato autorizado por Ventas para ejecutar la compensacion en Caja.",
        ))

    def refresh(self) -> None:
        return None

    def _execute_refund(self) -> None:
        dialog = CashRefundDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return
        data = dialog.result_value()
        try:
            result = self._presenter.execute_cash_refund(
                refund_id=data.refund_id,
                sale_id=data.sale_id,
                authorized_by=data.authorized_by,
                original_payment_lines=data.original_payment_lines,
                refund_lines=data.refund_lines,
                reason=data.reason,
            )
        except CashRegisterError as exc:
            QMessageBox.warning(self, "Caja", str(exc))
            return
        cash = getattr(result, "cash_amount", "0")
        entry_id = getattr(result, "ledger_entry_id", None)
        QMessageBox.information(
            self,
            "Caja",
            f"Reembolso ejecutado. Efectivo: {cash}. Ledger: {entry_id or 'sin salida fisica'}.",
        )
