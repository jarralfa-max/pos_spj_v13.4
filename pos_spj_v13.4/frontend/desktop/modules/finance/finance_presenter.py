"""FinancePresenter — the only gateway between the finance UI and the backend.

The presenter receives ALREADY-CONSTRUCTED query services and the authorized
command service (wired in ``finance_routes``). It never touches SQL,
connections or the app container, and returns display-ready view models to the
pages.

Auditoría d9f2bca F02: los comandos ya no llaman casos de uso directamente.
Pasan por ``FinanceCommandService``, que exige actor autenticado y el permiso
``FINANZAS.<accion>`` de cada operación. Sin servicio de comandos (o sin
sesión), todo comando se rechaza: nunca hay un actor "desktop" por omisión.
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
                 session_context=None, commands=None, embedded_presenters: dict | None = None,
                 ) -> None:
        """``connection_provider``: zero-arg callable owned by the composition
        root, used only for read-side summaries. ``commands``: the authorized
        ``FinanceCommandService``; ``use_cases`` is kept for callers that only
        read (it is never used to bypass authorization)."""
        self._conn = connection_provider
        self._queries = query_services
        self._use_cases = use_cases
        self._session = session_context
        self._commands = commands
        self._embedded = embedded_presenters or {}

    # ── sub-module wiring (suppliers is a page inside Finanzas) ────────────
    def connection(self):
        """Compatibilidad: la página de proveedores recibe ya su presentador
        construido (``embedded_presenter``, auditoría F26). Se conserva para
        llamadores antiguos."""
        return self._conn()

    def embedded_presenter(self, name: str):
        """Presentador de un submódulo compuesto en ``finance_routes`` (se
        construye la primera vez que se pide)."""
        value = self._embedded.get(name)
        if callable(value) and not hasattr(value, "ensure_loaded"):
            try:
                value = value()
            except Exception:
                logger.exception("No se pudo componer el submódulo %s", name)
                return None
            self._embedded[name] = value
        return value

    def session_context(self):
        return self._session

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

    def _command(self, name: str, *args, **kwargs) -> tuple[bool, str]:
        if self._commands is None:
            return False, "Finanzas no tiene servicio de comandos autorizado; operación rechazada."
        return self._run(getattr(self._commands, name), *args, **kwargs)

    def can(self, permission: str) -> bool:
        """Para habilitar/deshabilitar acciones en pantalla (la decisión real
        la vuelve a tomar el servicio de comandos)."""
        return bool(self._commands is not None and self._commands.can(permission))

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

    def journal_entries_count(self, *, status: str | None = None, search: str = "") -> int:
        return self._queries["journal"].count_entries(status=status, search=search or None)

    def journal_entries(self, *, status: str | None = None, search: str = "",
                        limit: int = 200, offset: int = 0) -> TableViewModel:
        rows, ids = [], []
        for entry in self._queries["journal"].list_entries(
                status=status, search=search or None, limit=limit, offset=offset):
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
    def open_receivables(self, *, customer_id: str | None = None,
                         search: str = "") -> TableViewModel:
        """CxC abiertas. ``customer_id`` filtra (el enlace desde CRM ya no sólo
        abre un resumen: filtra la tabla, F24); el cliente se muestra por
        nombre, no por un UUID truncado."""
        rows, ids = [], []
        names = self._customer_names()
        needle = (search or "").strip().lower()
        for receivable in self._queries["receivables"].open_receivables(customer_id=customer_id):
            name = names.get(receivable["customer_id"]) or receivable["customer_id"][:8]
            if needle and needle not in receivable["document_number"].lower() \
                    and needle not in name.lower():
                continue
            rows.append([receivable["document_number"], name,
                         receivable["issue_date"], receivable["due_date"] or "",
                         money_display(receivable["original_amount"]),
                         money_display(receivable["outstanding_amount"]),
                         status_es(receivable["status"])])
            ids.append(receivable["id"])
        return TableViewModel(rows, ids)

    def _customer_names(self) -> dict:
        resolver = self._queries.get("customer_names")
        if resolver is None:
            return {}
        try:
            return resolver()
        except Exception:
            logger.debug("customer names unavailable", exc_info=True)
            return {}

    def collection_history(self, *, search: str = "", limit: int = 200,
                           offset: int = 0) -> TableViewModel:
        """Historial de cobros (F23): permanece aunque la factura se liquide."""
        rows, ids = [], []
        names = self._customer_names()
        for row in self._queries["receivables"].collection_history(
                search=search or None, limit=limit, offset=offset):
            rows.append([row["collection_date"], row["reference"] or "",
                         row["document_number"],
                         names.get(row["customer_id"]) or row["customer_id"][:8],
                         money_display(row["amount"]), row["currency_code"],
                         row["treasury_account_name"] or "", row["entry_number"] or "",
                         status_es(row["receivable_status"])])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    def crm_receivable_summary(self, cliente_id: str) -> dict | None:
        """CRM-21: exposure/overdue/next-due-date summary from
        ``CustomerAccountsReceivableSummaryQuery`` (CRM-8/13), read directly
        against ``cuentas_por_cobrar`` (real production CxC data) — separate
        from, and not a replacement for, ``open_receivables()`` above, which
        reads the newer ``receivables`` table this Finanzas UI otherwise
        shows. Called with the LEGACY ``cliente_id`` (the id
        ``cuentas_por_cobrar.cliente_id`` actually holds), not the new
        Customer Master id — see the query's own docstring. Returns
        ``None`` if the customer has no CxC exposure or the lookup fails;
        never raises to the UI."""
        try:
            from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
                CustomerAccountsReceivableSummaryQuery,
            )
            summary = CustomerAccountsReceivableSummaryQuery(self._conn()).get_summary(
                str(cliente_id))
        except Exception as e:
            logger.debug("crm_receivable_summary unavailable for %s: %s", cliente_id, e)
            return None
        return {
            "customer_id": summary.customer_id,
            "current_exposure": money_display(summary.current_exposure),
            "overdue_amount": money_display(summary.overdue_amount),
            "next_due_date": summary.next_due_date,
            "receivable_status": summary.receivable_status,
        }

    def register_collection(self, *, receivable_id: str, amount: str,
                            treasury_account_id: str, reference: str) -> tuple[bool, str]:
        return self._command("register_collection", receivable_id=receivable_id,
                             amount=amount, treasury_account_id=treasury_account_id,
                             reference=reference)

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
        return self._command("schedule_payment", payable_id=payable_id, amount=amount,
                             treasury_account_id=treasury_account_id,
                             scheduled_date=scheduled_date, reference=reference)

    def authorize_supplier_payment(self, payment_id: str) -> tuple[bool, str]:
        return self._command("authorize_payment", payment_id)

    def execute_supplier_payment(self, payment_id: str, *,
                                 execution_reference: str = "") -> tuple[bool, str]:
        return self._command("execute_payment", payment_id,
                             execution_reference=execution_reference)

    # ── treasury ──────────────────────────────────────────────────────────
    def treasury_position(self) -> TableViewModel:
        rows, ids = [], []
        for account in self._queries["treasury"].treasury_position():
            balance = money_display(account["balance"])
            if account.get("shared_mirror"):
                balance = f"{balance} (saldo colectivo: espejo compartido)"
            rows.append([account["name"], account["account_type"], balance,
                         account["currency_code"]])
            ids.append(account["id"])
        return TableViewModel(rows, ids)

    def treasury_accounts(self) -> list[tuple[str, str]]:
        """Para los selectores: nombre, saldo y moneda visibles (F24)."""
        return [(row["id"],
                 f"{row['name']} — {money_display(row['balance'])} {row['currency_code']}")
                for row in self._queries["treasury"].treasury_position()]

    def register_treasury_transfer(self, *, source_id: str, target_id: str,
                                   amount: str, reference: str) -> tuple[bool, str]:
        return self._command("treasury_transfer", source_id=source_id, target_id=target_id,
                             amount=amount, reference=reference)

    # ── reconciliation ────────────────────────────────────────────────────
    def reconciliations(self) -> TableViewModel:
        rows, ids = [], []
        for row in self._queries["reconciliation"].list_reconciliations():
            rows.append([row["treasury_account_name"], status_es(row["status"]),
                         row["completed_by"] or "", row["completed_at"] or ""])
            ids.append(row["id"])
        return TableViewModel(rows, ids)

    def reconciliation_status(self, reconciliation_id: str) -> str:
        for row in self._queries["reconciliation"].list_reconciliations():
            if row["id"] == reconciliation_id:
                return str(row["status"])
        return ""

    def bank_statements(self, treasury_account_id: str) -> list[tuple[str, str]]:
        return [(row["id"], f"{row['statement_date']} — saldo final "
                            f"{money_display(row['closing_balance'])}")
                for row in self._queries["treasury"].statements(treasury_account_id)]

    def import_bank_statement(self, *, treasury_account_id: str, statement_date: date,
                              opening_balance: str, closing_balance: str,
                              lines: list[dict]) -> tuple[bool, str]:
        return self._command("import_statement", treasury_account_id=treasury_account_id,
                             statement_date=statement_date, opening_balance=opening_balance,
                             closing_balance=closing_balance, lines=lines)

    def start_reconciliation(self, bank_statement_id: str) -> tuple[bool, str]:
        return self._command("start_reconciliation", bank_statement_id)

    def reconciliation_candidates(self, reconciliation_id: str) -> dict:
        """``{"statement": TableViewModel, "ledger": TableViewModel}`` lado a lado."""
        empty = {"statement": TableViewModel([], []), "ledger": TableViewModel([], [])}
        if self._commands is None:
            return empty
        try:
            data = self._commands.reconciliation_candidates(reconciliation_id)
        except FinanceDomainError:
            return empty
        statement = TableViewModel(
            [[l["transaction_date"], l["description"], money_display(l["amount"]),
              l["external_reference"]] for l in data["statement_lines"]],
            [l["id"] for l in data["statement_lines"]])
        ledger = TableViewModel(
            [[l["entry_date"], l["entry_number"], l["description"] or "",
              money_display(l["debit_amount"]), money_display(l["credit_amount"])]
             for l in data["ledger_lines"]],
            [l["journal_line_id"] for l in data["ledger_lines"]])
        return {"statement": statement, "ledger": ledger}

    def match_reconciliation(self, *, reconciliation_id: str, bank_statement_line_id: str,
                             journal_line_id: str) -> tuple[bool, str]:
        return self._command("match", reconciliation_id=reconciliation_id,
                             bank_statement_line_id=bank_statement_line_id,
                             journal_line_id=journal_line_id)

    def complete_reconciliation(self, reconciliation_id: str, *,
                                difference_reason: str = "") -> tuple[bool, str]:
        return self._command("complete_reconciliation", reconciliation_id,
                             difference_reason=difference_reason or None)

    def revert_reconciliation(self, reconciliation_id: str, reason: str) -> tuple[bool, str]:
        return self._command("revert_reconciliation", reconciliation_id, reason=reason)

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
        return self._command("expense_request", account_id=account_id, amount=amount)

    def postable_expense_accounts(self) -> list[tuple[str, str]]:
        return [
            (row["id"], f"{row['code']} — {row['name']}")
            for row in self._queries["accounts"].postable_accounts()
            if str(row["account_type"]) in ("EXPENSE", "OTHER_EXPENSE", "COST_OF_SALES")
        ]

    # ── capital / assets ──────────────────────────────────────────────────
    def register_capital_contribution(self, *, amount: str, treasury_account_id: str,
                                      contributor: str) -> tuple[bool, str]:
        return self._command("capital_contribution", amount=amount,
                             treasury_account_id=treasury_account_id, contributor=contributor)

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
        return self._command("run_depreciation", year, month)

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
        return self._command("close_period", year, month, soft=soft)

    def reopen_period(self, year: int, month: int, reason: str) -> tuple[bool, str]:
        return self._command("reopen_period", year, month, reason=reason)

    def reverse_entry(self, journal_entry_id: str, reason: str) -> tuple[bool, str]:
        return self._command("reverse_entry", journal_entry_id, reason=reason)
