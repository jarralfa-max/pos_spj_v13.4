"""Capital, préstamos y CAPEX (§17): aportaciones, retiros, préstamos y sus
pagos; nada de esto es ingreso. CAPEX por proyecto desde los activos."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class CapitalPage(FinancePage):
    title = "Capital y préstamos"
    subtitle = "Movimientos de capital y financiamiento, con su asiento"
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Contraparte"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Intereses", "numeric"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Asiento", "date"),
    ]
    header_actions = [("Registrar movimiento", P.CAPITAL_REGISTER, "_register", True)]

    def _build_extra(self) -> None:
        for title, attr, columns in (
            ("Préstamos", "_loans", [ColumnSpec("Acreedor"), ColumnSpec("Principal", "numeric"),
                                     ColumnSpec("Saldo", "numeric"), ColumnSpec("Inicio", "date"),
                                     ColumnSpec("Vencimiento", "date"),
                                     ColumnSpec("Estado", "status")]),
            ("CAPEX por proyecto", "_capex", [ColumnSpec("Proyecto", "date"), ColumnSpec("Nombre"),
                                              ColumnSpec("CAPEX", "numeric")]),
        ):
            label = QLabel(title, self)
            label.setProperty("role", "muted")
            self._layout.addWidget(label)
            table = StandardTable(columns, self)
            table.setMaximumHeight(140)
            setattr(self, attr, table)
            self._layout.addWidget(table)

    def _load(self) -> None:
        self.set_table(self._presenter.capital_transactions())
        loans = self._presenter.loans()
        self._loans.load_rows(loans.rows, row_ids=loans.row_ids)
        self._capex.load_rows(self._presenter.capex_by_project().rows)

    def _register(self) -> None:
        p = self._presenter
        values = ask(self, "Movimiento de capital o financiamiento", [
            FieldSpec("kind", "Tipo", "combo", required=True, options=p.capital_kind_options()),
            FieldSpec("amount", "Importe (principal)", "money", required=True),
            FieldSpec("treasury_account_id", "Cuenta de tesorería", "combo", required=True,
                      options=p.treasury_accounts(money_only=True)),
            FieldSpec("counterparty", "Socio / acreedor"),
            FieldSpec("interest_amount", "Intereses (pago de préstamo)", "money",
                      allow_zero=True),
            FieldSpec("loan_id", "Préstamo (pago de préstamo)", "combo", options=p.open_loans()),
            FieldSpec("maturity_date", "Vencimiento (préstamo recibido)", "date",
                      default=p.today()),
        ], validator=_capital_rules)
        if values:
            if values["interest_amount"] in ("0", "0.00"):
                values["interest_amount"] = None
            if values["kind"] != "LOAN_RECEIVED":
                values["maturity_date"] = None
            self.run(p.register_capital_movement(**values))


def _capital_rules(values: dict) -> str | None:
    if values["kind"] == "LOAN_REPAYMENT" and not values["loan_id"]:
        return "Elija el préstamo que se paga."
    if values["kind"] in ("CONTRIBUTION", "WITHDRAWAL", "LOAN_RECEIVED") \
            and not values["counterparty"]:
        return "Indique el socio o el acreedor."
    return None
