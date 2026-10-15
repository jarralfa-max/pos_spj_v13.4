"""Bonos, comisiones, ajustes y préstamos — lo que la nómina toma además del
cálculo de asistencia. Captura y aprobación las hacen personas distintas."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.hr.dialogs.hr_operation_dialogs import LoanDialog, PayrollInputDialog
from frontend.desktop.modules.hr.pages._page_base import HRPage


class PayrollInputsPage(HRPage):
    title = "Conceptos y préstamos"
    subtitle = "Bonos, comisiones y ajustes por aprobar; préstamos y anticipos con su saldo"
    columns = [ColumnSpec("Empleado"), ColumnSpec("Concepto"), ColumnSpec("Importe", "numeric"),
               ColumnSpec("Fecha", "date"), ColumnSpec("Motivo"), ColumnSpec("Estado", "status")]
    empty_message = "No hay conceptos capturados"

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Capturar concepto"), "input_capture",
                         self._capture)
        self._add_action(create_success_button(self, "Aprobar"), "input_approve",
                         lambda: self._resolve(True))
        self._add_action(create_danger_button(self, "Rechazar"), "input_approve",
                         lambda: self._resolve(False))
        self._add_action(create_secondary_button(self, "Préstamo / anticipo"), "loan_grant",
                         self._grant_loan)

    def _build_extra(self) -> None:
        box = QWidget(self)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Préstamos y anticipos", box))
        self._loans = StandardTable([
            ColumnSpec("Empleado"), ColumnSpec("Tipo"), ColumnSpec("Importe", "numeric"),
            ColumnSpec("Abono", "numeric"), ColumnSpec("Saldo", "numeric"),
            ColumnSpec("Otorgado", "date"), ColumnSpec("Estado", "status")], box)
        layout.addWidget(self._loans)
        self._layout.addWidget(box)

    def _load(self) -> None:
        self.set_table(self._presenter.payroll_inputs())
        loans = self._presenter.loans()
        self._loans.load_rows(loans.rows, row_ids=loans.row_ids)

    def _capture(self) -> None:
        dialog = PayrollInputDialog(self._presenter.search_employees, self,
                                    on_submit=lambda v: self._presenter.capture_input(**v))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Concepto capturado"))
            self.reload()

    def _resolve(self, approve: bool) -> None:
        input_id = self.selected_id()
        if not input_id:
            self.notify(False, "Seleccione un concepto.")
            return
        ok, message = self._presenter.resolve_input(input_id, approve=approve)
        self.notify(ok, message)
        if ok:
            self.reload()

    def _grant_loan(self) -> None:
        dialog = LoanDialog(self._presenter.search_employees, self,
                            on_submit=lambda v: self._presenter.grant_loan(**v))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Préstamo registrado"))
            self.reload()
