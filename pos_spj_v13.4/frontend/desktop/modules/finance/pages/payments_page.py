"""Pagos a proveedor (§12–13): programar, autorizar y ejecutar son pasos
separados con segregación de funciones; la ejecución exige evidencia."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P

_STATUS = [("SCHEDULED", "Programado"), ("AUTHORIZED", "Autorizado"),
           ("EXECUTED", "Ejecutado"), ("CANCELLED", "Cancelado")]


class PaymentsPage(FinancePage):
    title = "Programación y autorizaciones"
    subtitle = "Quien programa no autoriza y quien autoriza no ejecuta"
    status_filter = _STATUS
    columns = [
        ColumnSpec("Documento", "date"),
        ColumnSpec("Proveedor"),
        ColumnSpec("Programado", "date"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Autorizó", "date"),
        ColumnSpec("Evidencia"),
    ]
    row_actions = [
        ("Autorizar", P.PAYMENT_AUTHORIZE, "_authorize"),
        ("Ejecutar", P.PAYMENT_EXECUTE, "_execute"),
        ("Cancelar", P.PAYMENT_SCHEDULE, "_cancel"),
    ]

    def _build_extra(self) -> None:
        label = QLabel("Pagos próximos a vencer", self)
        label.setProperty("role", "muted")
        self._layout.addWidget(label)
        self._upcoming = StandardTable([
            ColumnSpec("Vence", "date"), ColumnSpec("Documento", "date"),
            ColumnSpec("Proveedor"), ColumnSpec("Saldo", "numeric"),
            ColumnSpec("Estado", "status"),
        ], self)
        self._upcoming.setMaximumHeight(160)
        self._layout.addWidget(self._upcoming)

    def _load(self) -> None:
        self.set_table(self._presenter.supplier_payments(status=self._status_id()))
        upcoming = self._presenter.upcoming_payments()
        self._upcoming.load_rows(upcoming.rows, row_ids=upcoming.row_ids)

    def _allowed_actions(self):
        allowed = super()._allowed_actions()
        status = self._presenter.payment_status(self.selected_id()) if self.selected_id() else ""
        by_status = {"SCHEDULED": {"Autorizar", "Cancelar"},
                     "AUTHORIZED": {"Ejecutar", "Cancelar"}}
        return allowed & by_status.get(status, set())

    def _authorize(self) -> None:
        self.run(self._presenter.authorize_supplier_payment(self.selected_id()))

    def _execute(self) -> None:
        values = ask(self, "Ejecutar pago", [
            FieldSpec("info", "", "info",
                      default="Registre la evidencia externa (folio SPEI, cheque o recibo);"
                              " sin ella el pago no se marca como ejecutado."),
            FieldSpec("execution_reference", "Evidencia del pago", required=True),
        ])
        if values:
            self.run(self._presenter.execute_supplier_payment(
                self.selected_id(), values["execution_reference"]))

    def _cancel(self) -> None:
        reason = ask_reason(self, "Cancelar pago programado")
        if reason:
            self.run(self._presenter.cancel_supplier_payment(self.selected_id(), reason))
