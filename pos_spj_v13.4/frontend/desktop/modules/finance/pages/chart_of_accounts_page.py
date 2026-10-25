"""Plan de cuentas jerárquico (§8.1): alta, edición y baja lógica."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.fields_dialog import FieldSpec, ask, ask_reason
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class ChartOfAccountsPage(FinancePage):
    title = "Plan de cuentas"
    subtitle = "Cuentas acumulativas y de detalle; las que tienen movimientos no cambian de tipo"
    searchable = True
    columns = [
        ColumnSpec("Código", "date"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Nivel", "status"),
        ColumnSpec("Conciliable", "status"),
        ColumnSpec("Con movimientos", "status"),
        ColumnSpec("Estado", "status"),
    ]
    header_actions = [("Nueva cuenta", P.ACCOUNT_MANAGE, "_create", True)]
    row_actions = [
        ("Editar", P.ACCOUNT_MANAGE, "_edit"),
        ("Activar / desactivar", P.ACCOUNT_MANAGE, "_toggle"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.chart_of_accounts(self._search.query()))

    def _create(self) -> None:
        p = self._presenter
        values = ask(self, "Nueva cuenta contable", [
            FieldSpec("code", "Código", required=True, placeholder="Ej. 6135"),
            FieldSpec("name", "Nombre", required=True),
            FieldSpec("account_type", "Tipo", "combo", required=True,
                      options=p.account_type_options()),
            FieldSpec("parent_account_id", "Cuenta padre (acumulativa)", "combo",
                      options=p.summary_accounts()),
            FieldSpec("posting_allowed", "Recibe movimientos (cuenta de detalle)", "check",
                      default=True),
            FieldSpec("reconciliation_required", "Requiere conciliación", "check"),
            FieldSpec("cash_flow_category", "Clasificación de flujo", "combo", required=True,
                      options=p.cash_flow_options(), default="NONE"),
        ])
        if values:
            self.run(p.create_account(**values))

    def _edit(self) -> None:
        account = self._presenter.account(self.selected_id())
        if account is None:
            return
        p = self._presenter
        values = ask(self, f"Editar cuenta {account['code']}", [
            FieldSpec("name", "Nombre", required=True, default=account["name"]),
            FieldSpec("account_type", "Tipo", "combo", required=True,
                      options=p.account_type_options(), default=account["account_type"]),
            FieldSpec("posting_allowed", "Recibe movimientos (cuenta de detalle)", "check",
                      default=bool(account["posting_allowed"])),
            FieldSpec("reconciliation_required", "Requiere conciliación", "check",
                      default=bool(account["reconciliation_required"])),
            FieldSpec("cash_flow_category", "Clasificación de flujo", "combo", required=True,
                      options=p.cash_flow_options(), default=account["cash_flow_category"]),
            FieldSpec("reason", "Motivo del cambio", "multiline", required=True),
        ])
        if values:
            self.run(p.update_account(account["id"], **values))

    def _toggle(self) -> None:
        account = self._presenter.account(self.selected_id())
        if account is None:
            return
        activate = not account["active"]
        reason = ask_reason(self, "Activar cuenta" if activate else "Desactivar cuenta")
        if reason:
            self.run(self._presenter.set_account_active(account["id"], activate, reason))
