"""CASH-7 opening and shift lifecycle page wired to backend use cases."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import (
    CashShiftOpeningDialog,
    SuspendCashShiftDialog,
)
from frontend.desktop.modules.cash_register.presentation import display_code, status_label, user_facing_error


class CashShiftsPage(QWidget):
    """Real UI for opening, suspending, resuming and preliminary closing shifts."""

    def __init__(self, query_service, *, presenter, parent=None):
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        capabilities = presenter.capabilities()

        root = QVBoxLayout(self)
        open_shift = create_primary_button(self, "Abrir turno")
        suspend = create_secondary_button(self, "Suspender")
        resume = create_secondary_button(self, "Reanudar")
        prepare_close = create_secondary_button(self, "Cierre preliminar")

        open_shift.setEnabled(bool(capabilities.shift_open))
        suspend.setEnabled(bool(capabilities.shift_suspend))
        resume.setEnabled(bool(capabilities.shift_resume))
        prepare_close.setEnabled(bool(capabilities.shift_prepare_close))

        open_shift.clicked.connect(self._request_open_shift)
        suspend.clicked.connect(self._request_suspend_shift)
        resume.clicked.connect(self._request_resume_shift)
        prepare_close.clicked.connect(self._request_prepare_close)

        root.addWidget(PageHeader(
            self,
            title="Apertura y turnos",
            subtitle="Apertura, fondo, asignacion activa, suspension, reanudacion y cierre preliminar.",
            actions=[prepare_close, resume, suspend, open_shift],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Apertura", "date"),
            ColumnSpec("Caja"),
            ColumnSpec("Cajon"),
            ColumnSpec("Terminal"),
            ColumnSpec("Cajero"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Fondo", "numeric"),
            ColumnSpec("Efectivo esperado", "numeric"),
        ], self)
        self._rows_by_id = {}
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value) -> str:
        if value is None:
            return "Oculto por arqueo"
        return f"${value:,.2f}"

    def refresh(self) -> None:
        listing = self._query.list_recent(
            branch_id=self._presenter.active_branch_id(),
            requester_user_id=self._presenter.actor_user_id(),
        )
        self._rows_by_id = {row.id: row for row in listing.rows}
        self._kpis.set_cards([
            KPIDTO("active", "Turnos activos", str(listing.active_count), listing.active_count),
            KPIDTO("total", "Turnos visibles", str(len(listing.rows)), len(listing.rows)),
        ])
        self._table.load_rows([
            [
                row.opened_at,
                row.register_name,
                row.drawer_name,
                row.terminal_name,
                row.cashier_name or display_code("USR", row.cashier_user_id),
                status_label(row.status),
                self._money(row.opening_amount),
                self._money(row.expected_cash),
            ]
            for row in listing.rows
        ], row_ids=[row.id for row in listing.rows])

    def _selected_or_active_shift_id(self) -> str | None:
        return self._table.selected_row_id() or self._presenter.optional_active_shift_id()

    def _request_open_shift(self) -> None:
        dialog = CashShiftOpeningDialog(self)
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            result = self._presenter.open_cash_shift(
                opening_amount=dialog.result_value().opening_amount,
            )
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", "Turno abierto"))
        self.refresh()

    def _request_suspend_shift(self) -> None:
        shift_id = self._selected_or_active_shift_id()
        if not shift_id:
            self._show_error("Selecciona un turno o configura un turno activo.")
            return
        dialog = SuspendCashShiftDialog(self, shift=self._rows_by_id.get(shift_id))
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            result = self._presenter.suspend_cash_shift(
                shift_id=shift_id,
                reason=dialog.result_value().reason,
            )
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", "Turno suspendido"))
        self.refresh()

    def _request_resume_shift(self) -> None:
        self._transition_without_dialog(
            action=lambda shift_id: self._presenter.resume_cash_shift(shift_id=shift_id),
            empty_message="Selecciona el turno suspendido a reanudar.",
            success_message="Turno reanudado",
        )

    def _request_prepare_close(self) -> None:
        self._transition_without_dialog(
            action=lambda shift_id: self._presenter.begin_cash_shift_closing(shift_id=shift_id),
            empty_message="Selecciona el turno abierto para pre-cierre.",
            success_message="Turno en cierre preliminar",
        )

    def _transition_without_dialog(self, *, action, empty_message: str, success_message: str) -> None:
        shift_id = self._selected_or_active_shift_id()
        if not shift_id:
            self._show_error(empty_message)
            return
        try:
            result = action(shift_id)
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", success_message))
        self.refresh()

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message))
