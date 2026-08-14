"""CASH-15 differences workflow page."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import (
    ExplainCashDifferenceDialog,
    ResolveCashDifferenceDialog,
)
from frontend.desktop.modules.cash_register.presentation import status_label, user_facing_error


class CashDifferencesPage(QWidget):
    def __init__(self, query_service, *, presenter, parent=None):
        super().__init__(parent)
        self._query = query_service
        self._presenter = presenter
        self._rows_by_id = {}
        root = QVBoxLayout(self)
        explain = create_secondary_button(self, "Explicar")
        review = create_secondary_button(self, "Revisar")
        resolve = create_secondary_button(self, "Resolver")
        caps = presenter.capabilities()
        explain.setEnabled(bool(caps.difference_explain))
        review.setEnabled(bool(caps.difference_review))
        resolve.setEnabled(bool(caps.difference_resolve))
        explain.clicked.connect(self._explain)
        review.clicked.connect(self._review)
        resolve.clicked.connect(self._resolve)
        root.addWidget(PageHeader(
            self,
            title="Diferencias",
            subtitle="Clasificacion, tolerancias, explicacion, revision independiente y resolucion.",
            actions=[resolve, review, explain],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._table = StandardTable([
            ColumnSpec("Estado", "status"), ColumnSpec("Clasificacion"),
            ColumnSpec("Severidad", "status"), ColumnSpec("Monto", "numeric"),
            ColumnSpec("Tolerancia", "numeric"), ColumnSpec("Recurrencia", "numeric"),
            ColumnSpec("Explicacion"), ColumnSpec("Resolucion"),
        ], self)
        root.addWidget(self._table)
        self.refresh()

    @staticmethod
    def _money(value):
        return f"${value:,.2f}"

    def refresh(self) -> None:
        rows = self._query.list_for_branch(
            branch_id=self._presenter.active_branch_id(),
            requester_user_id=self._presenter.actor_user_id(),
        )
        self._rows_by_id = {row.id: row for row in rows}
        pending = sum(1 for row in rows if row.status != "RESOLVED")
        critical = sum(1 for row in rows if row.severity == "CRITICAL")
        self._kpis.set_cards([
            KPIDTO("pending", "Pendientes", str(pending), pending),
            KPIDTO("critical", "Criticas", str(critical), critical),
            KPIDTO("total", "Diferencias", str(len(rows)), len(rows)),
        ])
        self._table.load_rows([
            [
                status_label(row.status), status_label(row.classification), status_label(row.severity),
                self._money(row.amount), self._money(row.tolerance_amount),
                row.recurrence_count, row.explanation or "-", row.resolution or "-",
            ]
            for row in rows
        ], row_ids=[row.id for row in rows])

    def _selected_difference_id(self) -> str | None:
        return self._table.selected_row_id()

    def _selected_difference(self):
        difference_id = self._selected_difference_id()
        return self._rows_by_id.get(difference_id or "")

    def _explain(self) -> None:
        self._run_text_transition(
            dialog_factory=lambda difference: ExplainCashDifferenceDialog(
                self, difference=difference),
            command=lambda difference_id, text: self._presenter.explain_cash_difference(
                difference_id=difference_id, explanation=text),
            success="Diferencia explicada",
        )

    def _review(self) -> None:
        difference_id = self._selected_difference_id()
        if not difference_id:
            return
        try:
            result = self._presenter.review_cash_difference(difference_id=difference_id)
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", "Diferencia en revision"))
        self.refresh()

    def _resolve(self) -> None:
        self._run_text_transition(
            dialog_factory=lambda difference: ResolveCashDifferenceDialog(
                self, difference=difference),
            command=lambda difference_id, text: self._presenter.resolve_cash_difference(
                difference_id=difference_id, resolution=text),
            success="Diferencia resuelta",
        )

    def _run_text_transition(self, *, dialog_factory, command, success: str) -> None:
        difference_id = self._selected_difference_id()
        if not difference_id:
            return
        difference = self._selected_difference()
        if difference is None:
            self._show_error("Selecciona una diferencia vigente.")
            return
        dialog = dialog_factory(difference)
        if dialog.exec_() != dialog.Accepted:
            return
        try:
            result = command(difference_id, dialog.result_value().reason)
        except CashRegisterError as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", success))
        self.refresh()

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message or "No fue posible completar la diferencia."))
