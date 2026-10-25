"""Gastos (§16): solicitud → aprobación (reglas configurables, compromete el
presupuesto) → devengo con su documento → pago. Cancelar libera el compromiso."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P

_STATUS = [("REQUESTED", "Solicitado"), ("APPROVED", "Aprobado"), ("ACCRUED", "Devengado"),
           ("SETTLED", "Liquidado"), ("REJECTED", "Rechazado"), ("CANCELLED", "Cancelado")]


class ExpensesPage(FinancePage):
    title = "Gastos"
    subtitle = "Solicitudes de gasto contra presupuesto"
    status_filter = _STATUS
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Categoría"),
        ColumnSpec("Concepto"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Devengado", "numeric"),
        ColumnSpec("Pagado", "numeric"),
        ColumnSpec("Aprobaciones", "status"),
        ColumnSpec("Estado", "status"),
    ]
    header_actions = [("Nueva solicitud", P.EXPENSE_REQUEST, "_request", True)]
    row_actions = [
        ("Aprobar", P.EXPENSE_APPROVE, "_approve"),
        ("Aprobar con exceso", P.BUDGET_AUTHORIZE_EXCESS, "_approve_excess"),
        ("Rechazar", P.EXPENSE_APPROVE, "_reject"),
        ("Devengar", P.EXPENSE_ACCRUE, "_accrue"),
        ("Cancelar", P.EXPENSE_REQUEST, "_cancel"),
    ]

    def _build_extra(self) -> None:
        label = QLabel("Reglas de aprobación", self)
        label.setProperty("role", "muted")
        self._layout.addWidget(label)
        self._rules = StandardTable([
            ColumnSpec("Regla"), ColumnSpec("Desde", "numeric"), ColumnSpec("Categoría"),
            ColumnSpec("Aprobaciones", "numeric"), ColumnSpec("Prioridad", "numeric"),
        ], self)
        self._rules.setMaximumHeight(140)
        self._layout.addWidget(self._rules)
        new_rule = create_secondary_button(self, "Nueva regla de aprobación")
        new_rule.clicked.connect(self._new_rule)
        self._guard(new_rule, P.SETTINGS_MANAGE)
        self._layout.addWidget(new_rule)

    def _load(self) -> None:
        self.set_table(self._presenter.expense_requests(status=self._status_id()))
        rules = self._presenter.approval_rules()
        self._rules.load_rows(rules.rows, row_ids=rules.row_ids)

    def _allowed_actions(self):
        allowed = super()._allowed_actions()
        status = self._presenter.expense_status(self.selected_id()) if self.selected_id() else ""
        by_status = {
            "REQUESTED": {"Aprobar", "Aprobar con exceso", "Rechazar", "Cancelar"},
            "APPROVED": {"Devengar", "Cancelar"},
        }
        return allowed & by_status.get(status, set())

    def _request(self) -> None:
        p = self._presenter
        values = ask(self, "Solicitud de gasto", [
            FieldSpec("account_id", "Cuenta de gasto", "combo", required=True,
                      options=p.expense_accounts()),
            FieldSpec("amount", "Importe", "money", required=True),
            FieldSpec("category", "Categoría"),
            FieldSpec("description", "Concepto", "multiline"),
            FieldSpec("cost_center_id", "Centro de costo", "combo",
                      options=p.dimension_options("cost_centers")),
            FieldSpec("project_id", "Proyecto", "combo", options=p.dimension_options("projects")),
            FieldSpec("department_id", "Departamento", "combo",
                      options=p.dimension_options("departments")),
        ])
        if values:
            self.run(p.register_expense_request(**values))

    def _approve(self) -> None:
        self.run(self._presenter.approve_expense(self.selected_id()))

    def _approve_excess(self) -> None:
        reason = ask_reason(self, "Aprobar excediendo el presupuesto", "Justificación del exceso")
        if reason:
            self.run(self._presenter.approve_expense(self.selected_id(), reason=reason,
                                                     authorize_excess=True))

    def _reject(self) -> None:
        reason = ask_reason(self, "Rechazar solicitud")
        if reason:
            self.run(self._presenter.reject_expense(self.selected_id(), reason))

    def _accrue(self) -> None:
        p = self._presenter
        values = ask(self, "Devengar gasto", [
            FieldSpec("document_reference", "Factura / documento", required=True),
            FieldSpec("amount", "Importe facturado (vacío: el aprobado)", "money",
                      allow_zero=True),
            FieldSpec("supplier_id", "Proveedor (a crédito)", "search",
                      provider=p.supplier_options),
            FieldSpec("paid_from_treasury_account_id", "O pagado desde", "combo",
                      options=p.treasury_accounts(money_only=True)),
        ], validator=lambda v: None if bool(v["supplier_id"]) != bool(
            v["paid_from_treasury_account_id"]) else
            "Indique el proveedor (a crédito) o la cuenta desde la que se pagó; uno solo.")
        if values:
            if values["amount"] in ("0", "0.00"):
                values["amount"] = None
            self.run(p.accrue_expense(self.selected_id(), **values))

    def _cancel(self) -> None:
        reason = ask_reason(self, "Cancelar solicitud")
        if reason:
            self.run(self._presenter.cancel_expense(self.selected_id(), reason))

    def _new_rule(self) -> None:
        values = ask(self, "Regla de aprobación de gastos", [
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("min_amount", "Aplica desde el importe", "money", allow_zero=True),
            FieldSpec("required_approvals", "Aprobaciones requeridas", "int", required=True,
                      minimum=1, maximum=5, default=1),
            FieldSpec("category", "Sólo para la categoría (vacío: todas)"),
            FieldSpec("priority", "Prioridad", "int", maximum=100),
        ])
        if values:
            values["category"] = values["category"] or None
            self.run(self._presenter.create_expense_rule(**values))
