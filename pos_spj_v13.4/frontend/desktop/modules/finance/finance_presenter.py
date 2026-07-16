"""FinancePresenter — the only gateway between the finance UI and the backend.

The presenter receives ALREADY-CONSTRUCTED query services and use cases (wired
in ``finance_routes``). It never touches SQL, connections or the app
container, and returns display-ready view models to the pages.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid
from frontend.desktop.modules.finance.finance_view_models import (
    INSTRUMENT_ES,
    KpiViewModel,
    TableViewModel,
    money_display,
    status_es,
)

logger = logging.getLogger("spj.finance.presenter")


class FinancePresenter:
    def __init__(self, *, connection_provider, query_services: dict, use_cases: dict,
                 session_context=None) -> None:
        """``connection_provider``: zero-arg callable owned by the composition
        root; the presenter forwards it to use cases without inspecting it."""
        self._conn = connection_provider
        self._queries = query_services
        self._use_cases = use_cases
        self._session = session_context

    # ── helpers ───────────────────────────────────────────────────────────
    def _run(self, action, *args, **kwargs) -> tuple[bool, str]:
        try:
            action(*args, **kwargs)
            return True, "Operación registrada correctamente."
        except FinanceDomainError as exc:
            return False, str(exc)
        except Exception:
            logger.exception("FinancePresenter: unexpected error")
            return False, "Error inesperado; revise el log."

    def _actor(self) -> str:
        user_id = getattr(self._session, "user_id", None)
        return str(user_id) if user_id else "desktop"

    @staticmethod
    def _month_bounds(today: date | None = None) -> tuple[str, str]:
        today = today or date.today()
        first = today.replace(day=1).isoformat()
        return first, today.isoformat()

    # ── overview ──────────────────────────────────────────────────────────
    def overview_kpis(self) -> list[KpiViewModel]:
        month_from, month_to = self._month_bounds()
        data = self._queries["dashboard"].overview(month_from=month_from, month_to=month_to)
        return [
            KpiViewModel("Ingresos del mes", money_display(data["revenue"]), "success"),
            KpiViewModel("Costo de ventas", money_display(data["cost_of_sales"]), "warning"),
            KpiViewModel("Gastos", money_display(data["expenses"]), "warning"),
            KpiViewModel("CxC abiertas", money_display(data["open_receivables"]), "primary"),
            KpiViewModel("CxP abiertas", money_display(data["open_payables"]), "primary"),
            KpiViewModel("Obligaciones comerciales",
                         money_display(data["open_commercial_obligations"]), "primary"),
        ]

    # ── chart of accounts / journal ───────────────────────────────────────
    def chart_of_accounts(self) -> TableViewModel:
        rows, ids = [], []
        for account in self._queries["accounts"].chart_of_accounts():
            rows.append([account["code"], account["name"], account["account_type"],
                         "Sí" if account["posting_allowed"] else "No",
                         "Activa" if account["active"] else "Inactiva"])
            ids.append(account["id"])
        return TableViewModel(rows, ids)

    def journal_entries(self, *, status: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for entry in self._queries["journal"].list_entries(status=status):
            rows.append([entry["entry_number"], entry["entry_date"],
                         entry["description"], entry["journal_type"],
                         money_display(entry["total"]), status_es(entry["status"])])
            ids.append(entry["id"])
        return TableViewModel(rows, ids)

    def journal_entry_lines(self, journal_entry_id: str) -> TableViewModel:
        rows = [
            [line["account_code"], line["account_name"], line["description"],
             money_display(line["debit_amount"]), money_display(line["credit_amount"])]
            for line in self._queries["journal"].entry_lines(journal_entry_id)
        ]
        return TableViewModel(rows, [])

    def general_ledger(self, account_id: str) -> TableViewModel:
        rows = [
            [line["entry_date"], line["entry_number"], line["description"] or
             line["entry_description"], money_display(line["debit_amount"]),
             money_display(line["credit_amount"])]
            for line in self._queries["ledger"].ledger_lines(account_id)
        ]
        return TableViewModel(rows, [])

    def trial_balance(self) -> TableViewModel:
        month_from, month_to = self._month_bounds()
        rows = [
            [row.account_code, row.account_name, row.account_type,
             money_display(row.debit_total), money_display(row.credit_total),
             money_display(row.balance)]
            for row in self._queries["statements"].trial_balance(
                date_from=None, date_to=month_to)
        ]
        return TableViewModel(rows, [])

    def fiscal_periods(self) -> TableViewModel:
        rows, ids = [], []
        for period in self._queries["journal"].fiscal_periods():
            rows.append([f"{period['year']:04d}-{period['month']:02d}",
                         status_es(period["status"]),
                         period["closed_at"] or "", period["reopen_reason"] or ""])
            ids.append(period["id"])
        return TableViewModel(rows, ids)

    # ── receivables / collections ─────────────────────────────────────────
    def open_receivables(self) -> TableViewModel:
        rows, ids = [], []
        for receivable in self._queries["receivables"].open_receivables():
            rows.append([receivable["document_number"], receivable["customer_id"][:8],
                         receivable["issue_date"], receivable["due_date"] or "",
                         money_display(receivable["original_amount"]),
                         money_display(receivable["outstanding_amount"]),
                         status_es(receivable["status"])])
            ids.append(receivable["id"])
        return TableViewModel(rows, ids)

    def register_collection(self, *, receivable_id: str, amount: str,
                            treasury_account_id: str, reference: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["register_collection"].execute, self._conn(),
            receivable_id=receivable_id, amount=amount,
            treasury_account_id=treasury_account_id,
            collection_date=date.today(), reference=reference,
            operation_id=new_uuid(),
        )

    # ── payables / payments ───────────────────────────────────────────────
    def open_payables(self) -> TableViewModel:
        rows, ids = [], []
        for payable in self._queries["payables"].open_payables():
            rows.append([payable["document_number"], payable["supplier_id"][:8],
                         payable["issue_date"], payable["due_date"] or "",
                         money_display(payable["original_amount"]),
                         money_display(payable["outstanding_amount"]),
                         status_es(payable["status"])])
            ids.append(payable["id"])
        return TableViewModel(rows, ids)

    def supplier_payments(self, *, status: str | None = None) -> TableViewModel:
        rows, ids = [], []
        for payment in self._queries["payables"].payments(status=status):
            rows.append([payment["reference"] or payment["id"][:8],
                         payment["supplier_id"][:8], payment["scheduled_date"],
                         money_display(payment["amount"]), status_es(payment["status"]),
                         payment["authorized_by"] or ""])
            ids.append(payment["id"])
        return TableViewModel(rows, ids)

    def schedule_supplier_payment(self, *, payable_id: str, amount: str,
                                  treasury_account_id: str, scheduled_date: date,
                                  reference: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["schedule_payment"].execute, self._conn(),
            payable_id=payable_id, amount=amount, scheduled_date=scheduled_date,
            treasury_account_id=treasury_account_id, scheduled_by=self._actor(),
            reference=reference, operation_id=new_uuid(),
        )

    def authorize_supplier_payment(self, payment_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["authorize_payment"].execute, self._conn(),
            payment_id=payment_id, authorized_by=self._actor(), operation_id=new_uuid(),
        )

    def execute_supplier_payment(self, payment_id: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["execute_payment"].execute, self._conn(),
            payment_id=payment_id, executed_date=date.today(), operation_id=new_uuid(),
        )

    # ── treasury ──────────────────────────────────────────────────────────
    def treasury_position(self) -> TableViewModel:
        rows, ids = [], []
        for account in self._queries["treasury"].treasury_position():
            rows.append([account["name"], account["account_type"],
                         money_display(account["balance"]), account["currency_code"]])
            ids.append(account["id"])
        return TableViewModel(rows, ids)

    def treasury_accounts(self) -> list[tuple[str, str]]:
        return [(row["id"], row["name"])
                for row in self._queries["treasury"].treasury_position()]

    def register_treasury_transfer(self, *, source_id: str, target_id: str,
                                   amount: str, reference: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["treasury_transfer"].execute, self._conn(),
            source_treasury_account_id=source_id, target_treasury_account_id=target_id,
            amount=amount, transfer_date=date.today(), reference=reference,
            operation_id=new_uuid(),
        )

    # ── reconciliation ────────────────────────────────────────────────────
    def reconciliations(self) -> TableViewModel:
        rows, ids = [], []
        for row in self._queries["reconciliation"].list_reconciliations():
            rows.append([row["treasury_account_name"], status_es(row["status"]),
                         row["completed_by"] or "", row["completed_at"] or ""])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    # ── budgets / expenses ───────────────────────────────────────────────
    def budgets(self) -> TableViewModel:
        rows, ids = [], []
        for budget in self._queries["budgets"].list_budgets():
            rows.append([budget["name"], str(budget["fiscal_year"]),
                         f"v{budget['version']}", status_es(budget["status"]),
                         budget["approved_by"] or ""])
            ids.append(budget["id"])
        return TableViewModel(rows, ids)

    def budget_execution(self, fiscal_year: int) -> TableViewModel:
        rows = [
            [row["period_code"], row["account_code"], row["account_name"],
             money_display(row["planned_amount"]), money_display(row["committed_amount"]),
             money_display(row["accrued_amount"]), money_display(row["available"])]
            for row in self._queries["budgets"].budget_execution(fiscal_year)
        ]
        return TableViewModel(rows, [])

    def register_expense_request(self, *, account_id: str, amount: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["expense_request"].execute, self._conn(),
            account_id=account_id, amount=amount, request_date=date.today(),
            operation_id=new_uuid(),
        )

    def postable_expense_accounts(self) -> list[tuple[str, str]]:
        return [
            (row["id"], f"{row['code']} — {row['name']}")
            for row in self._queries["accounts"].postable_accounts()
            if str(row["account_type"]) in ("EXPENSE", "OTHER_EXPENSE", "COST_OF_SALES")
        ]

    # ── capital / assets ──────────────────────────────────────────────────
    def register_capital_contribution(self, *, amount: str, treasury_account_id: str,
                                      contributor: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["capital_contribution"].execute, self._conn(),
            amount=amount, contribution_date=date.today(),
            treasury_account_id=treasury_account_id, contributor=contributor,
            operation_id=new_uuid(),
        )

    def fixed_assets(self) -> TableViewModel:
        rows, ids = [], []
        for asset in self._queries["assets"].list_assets():
            rows.append([asset["name"], money_display(asset["acquisition_cost"]),
                         money_display(asset["accumulated_depreciation"]),
                         money_display(asset["net_book_value"]),
                         status_es(asset["status"]),
                         asset["last_depreciated_period"] or ""])
            ids.append(asset["id"])
        return TableViewModel(rows, ids)

    def run_depreciation(self, year: int, month: int) -> tuple[bool, str]:
        return self._run(
            self._use_cases["run_depreciation"].execute, self._conn(),
            year=year, month=month, operation_id=new_uuid(),
        )

    # ── commercial instruments ───────────────────────────────────────────
    def commercial_obligations(self) -> TableViewModel:
        rows, ids = [], []
        for obligation in self._queries["obligations"].open_obligations():
            rows.append([
                INSTRUMENT_ES.get(obligation["instrument_type"], obligation["instrument_type"]),
                obligation["source_instrument_id"][:8],
                money_display(obligation["recognized_amount"]),
                money_display(obligation["redeemed_amount"]),
                money_display(obligation["outstanding"]),
                status_es(obligation["status"]),
                obligation["expires_at"] or "",
            ])
            ids.append(obligation["id"])
        return TableViewModel(rows, ids)

    def instrument_summary(self) -> TableViewModel:
        rows = [
            [INSTRUMENT_ES.get(row["instrument_type"], row["instrument_type"]),
             str(row["instruments"]), money_display(row["recognized"]),
             money_display(row["redeemed"]), money_display(row["released"]),
             money_display(row["outstanding"])]
            for row in self._queries["obligations"].summary_by_instrument()
        ]
        return TableViewModel(rows, [])

    def posting_profiles(self) -> TableViewModel:
        rows, ids = [], []
        for profile in self._queries["obligations"].posting_profiles():
            rows.append([profile["profile_key"], profile["description"],
                         profile["instrument_type"] or "—", profile["effective_from"],
                         profile["effective_to"] or "Vigente",
                         "Activo" if profile["active"] else "Inactivo"])
            ids.append(profile["id"])
        return TableViewModel(rows, ids)

    def integration_exceptions(self) -> TableViewModel:
        rows = [
            [row["event_name"], row["event_id"][:8], row["processed_at"]]
            for row in self._queries["obligations"].events_without_entry()
        ]
        return TableViewModel(rows, [])

    # ── statements ────────────────────────────────────────────────────────
    def balance_sheet(self) -> dict:
        _, month_to = self._month_bounds()
        return self._queries["statements"].balance_sheet(as_of=month_to)

    def income_statement(self) -> dict:
        month_from, month_to = self._month_bounds()
        return self._queries["statements"].income_statement(
            date_from=None, date_to=month_to)

    def cash_flow_statement(self) -> dict:
        month_from, month_to = self._month_bounds()
        return self._queries["statements"].cash_flow_statement(
            date_from=month_from, date_to=month_to)

    # ── periods / manual entries ─────────────────────────────────────────
    def close_period(self, year: int, month: int, *, soft: bool) -> tuple[bool, str]:
        return self._run(
            self._use_cases["close_period"].execute, self._conn(), year, month,
            closed_by=self._actor(), operation_id=new_uuid(), soft=soft,
        )

    def reopen_period(self, year: int, month: int, reason: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["reopen_period"].execute, self._conn(), year, month,
            reason=reason, operation_id=new_uuid(),
        )

    def reverse_entry(self, journal_entry_id: str, reason: str) -> tuple[bool, str]:
        return self._run(
            self._use_cases["reverse_entry"], journal_entry_id, reason,
        )
