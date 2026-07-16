"""Canonical read-only query services for the finance bounded context.

Consumers: desktop UI pages and BI (read-only, §21). BI never writes to the
ledger and never queries finance tables directly — it goes through these
services and their stable row shapes.
"""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
)


class AccountQueryService(FinanceQueryServiceBase):
    def chart_of_accounts(self) -> list[dict]:
        return self._query(
            "SELECT id, code, name, account_type, normal_balance, posting_allowed,"
            " reconciliation_required, cash_flow_category, active"
            " FROM accounts ORDER BY code"
        )

    def postable_accounts(self) -> list[dict]:
        return self._query(
            "SELECT id, code, name, account_type FROM accounts"
            " WHERE active=1 AND posting_allowed=1 ORDER BY code"
        )


class JournalQueryService(FinanceQueryServiceBase):
    def list_entries(self, *, status: str | None = None, journal_type: str | None = None,
                     date_from: str | None = None, date_to: str | None = None,
                     limit: int = 200, offset: int = 0) -> list[dict]:
        conditions = ["1=1"]
        params: list = []
        if status:
            conditions.append("je.status = ?")
            params.append(status)
        if journal_type:
            conditions.append("j.journal_type = ?")
            params.append(journal_type)
        if date_from:
            conditions.append("je.entry_date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("je.entry_date <= ?")
            params.append(date_to)
        params.extend([limit, offset])
        return self._query(
            "SELECT je.id, je.entry_number, je.entry_date, je.description, je.status,"
            " j.journal_type, je.source_module, je.posting_purpose, je.branch_id,"
            " (SELECT COALESCE(SUM(CAST(debit_amount AS NUMERIC)),0)"
            "    FROM journal_lines WHERE journal_entry_id = je.id) AS total"
            " FROM journal_entries je JOIN journals j ON j.id = je.journal_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY je.entry_date DESC, je.entry_number DESC LIMIT ? OFFSET ?",
            tuple(params),
        )

    def entry_lines(self, journal_entry_id: str) -> list[dict]:
        return self._query(
            "SELECT jl.line_index, a.code AS account_code, a.name AS account_name,"
            " jl.description, jl.debit_amount, jl.credit_amount"
            " FROM journal_lines jl JOIN accounts a ON a.id = jl.account_id"
            " WHERE jl.journal_entry_id = ? ORDER BY jl.line_index",
            (journal_entry_id,),
        )

    def fiscal_periods(self) -> list[dict]:
        return self._query(
            "SELECT id, year, month, status, closed_at, closed_by, reopen_reason"
            " FROM fiscal_periods ORDER BY year DESC, month DESC"
        )


class ReceivableQueryService(FinanceQueryServiceBase):
    def open_receivables(self, *, customer_id: str | None = None) -> list[dict]:
        conditions = ["r.status IN ('OPEN','PARTIALLY_COLLECTED')"]
        params: list = []
        if customer_id:
            conditions.append("r.customer_id = ?")
            params.append(customer_id)
        return self._query(
            "SELECT r.id, r.customer_id, fd.document_number, r.original_amount,"
            " r.outstanding_amount, r.issue_date, r.due_date, r.status, r.branch_id"
            " FROM receivables r JOIN financial_documents fd ON fd.id = r.financial_document_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY r.issue_date",
            tuple(params),
        )

    def aging(self, as_of: str) -> list[dict]:
        return self._query(
            "SELECT r.id, r.customer_id, r.outstanding_amount, r.due_date,"
            " CASE"
            "  WHEN r.due_date IS NULL OR r.due_date >= ? THEN 'CURRENT'"
            "  WHEN julianday(?) - julianday(r.due_date) <= 30 THEN '1-30'"
            "  WHEN julianday(?) - julianday(r.due_date) <= 60 THEN '31-60'"
            "  WHEN julianday(?) - julianday(r.due_date) <= 90 THEN '61-90'"
            "  ELSE '90+'"
            " END AS bucket"
            " FROM receivables r WHERE r.status IN ('OPEN','PARTIALLY_COLLECTED')",
            (as_of, as_of, as_of, as_of),
        )

    def collections_by_receivable(self, receivable_id: str) -> list[dict]:
        return self._query(
            "SELECT id, amount, collection_date, reference, treasury_account_id"
            " FROM collections WHERE receivable_id = ? ORDER BY collection_date",
            (receivable_id,),
        )


class PayableQueryService(FinanceQueryServiceBase):
    def open_payables(self, *, supplier_id: str | None = None) -> list[dict]:
        conditions = ["p.status IN ('OPEN','SCHEDULED','PARTIALLY_PAID')"]
        params: list = []
        if supplier_id:
            conditions.append("p.supplier_id = ?")
            params.append(supplier_id)
        return self._query(
            "SELECT p.id, p.supplier_id, fd.document_number, p.original_amount,"
            " p.outstanding_amount, p.issue_date, p.due_date, p.status, p.branch_id"
            " FROM payables p JOIN financial_documents fd ON fd.id = p.financial_document_id"
            f" WHERE {' AND '.join(conditions)} ORDER BY p.due_date, p.issue_date",
            tuple(params),
        )

    def payments(self, *, status: str | None = None) -> list[dict]:
        if status:
            return self._query(
                "SELECT id, payable_id, supplier_id, amount, scheduled_date, status,"
                " scheduled_by, authorized_by, executed_date, reference"
                " FROM supplier_payments WHERE status = ? ORDER BY scheduled_date",
                (status,),
            )
        return self._query(
            "SELECT id, payable_id, supplier_id, amount, scheduled_date, status,"
            " scheduled_by, authorized_by, executed_date, reference"
            " FROM supplier_payments ORDER BY scheduled_date DESC LIMIT 200"
        )


class TreasuryQueryService(FinanceQueryServiceBase):
    def treasury_position(self) -> list[dict]:
        """Balance per treasury account computed from its POSTED ledger mirror."""
        return self._query(
            "SELECT ta.id, ta.name, ta.account_type, ta.currency_code, ta.branch_id,"
            " COALESCE(SUM(CAST(jl.debit_amount AS NUMERIC)"
            "   - CAST(jl.credit_amount AS NUMERIC)), 0) AS balance"
            " FROM treasury_accounts ta"
            " LEFT JOIN journal_lines jl ON jl.account_id = ta.ledger_account_id"
            " LEFT JOIN journal_entries je ON je.id = jl.journal_entry_id"
            "   AND je.status IN ('POSTED','REVERSED')"
            " WHERE ta.active = 1"
            " GROUP BY ta.id, ta.name, ta.account_type, ta.currency_code, ta.branch_id"
            " ORDER BY ta.name"
        )

    def statements(self, treasury_account_id: str) -> list[dict]:
        return self._query(
            "SELECT id, statement_date, opening_balance, closing_balance, imported_at"
            " FROM bank_statements WHERE treasury_account_id = ?"
            " ORDER BY statement_date DESC",
            (treasury_account_id,),
        )


class ReconciliationQueryService(FinanceQueryServiceBase):
    def list_reconciliations(self, *, status: str | None = None) -> list[dict]:
        if status:
            return self._query(
                "SELECT r.id, r.treasury_account_id, ta.name AS treasury_account_name,"
                " r.bank_statement_id, r.status, r.completed_by, r.completed_at"
                " FROM reconciliations r JOIN treasury_accounts ta ON ta.id = r.treasury_account_id"
                " WHERE r.status = ? ORDER BY r.created_at DESC",
                (status,),
            )
        return self._query(
            "SELECT r.id, r.treasury_account_id, ta.name AS treasury_account_name,"
            " r.bank_statement_id, r.status, r.completed_by, r.completed_at"
            " FROM reconciliations r JOIN treasury_accounts ta ON ta.id = r.treasury_account_id"
            " ORDER BY r.created_at DESC LIMIT 100"
        )

    def unmatched_statement_lines(self, bank_statement_id: str) -> list[dict]:
        return self._query(
            "SELECT id, transaction_date, description, amount, external_reference"
            " FROM bank_statement_lines"
            " WHERE bank_statement_id = ? AND reconciled = 0 ORDER BY line_index",
            (bank_statement_id,),
        )


class BudgetQueryService(FinanceQueryServiceBase):
    def budget_execution(self, fiscal_year: int) -> list[dict]:
        """BudgetExecutionQueryService rows: planned vs committed vs accrued."""
        return self._query(
            "SELECT b.id AS budget_id, b.name, b.status, bl.period_code,"
            " a.code AS account_code, a.name AS account_name,"
            " bl.planned_amount, bl.committed_amount, bl.accrued_amount,"
            " CAST(bl.planned_amount AS NUMERIC) - CAST(bl.committed_amount AS NUMERIC)"
            "   - CAST(bl.accrued_amount AS NUMERIC) AS available"
            " FROM budgets b JOIN budget_lines bl ON bl.budget_id = b.id"
            " JOIN accounts a ON a.id = bl.account_id"
            " WHERE b.fiscal_year = ? AND b.status = 'APPROVED'"
            " ORDER BY bl.period_code, a.code",
            (fiscal_year,),
        )

    def list_budgets(self) -> list[dict]:
        return self._query(
            "SELECT id, name, fiscal_year, version, status, approved_by, approved_at"
            " FROM budgets ORDER BY fiscal_year DESC, version DESC"
        )


class FixedAssetQueryService(FinanceQueryServiceBase):
    def list_assets(self) -> list[dict]:
        return self._query(
            "SELECT id, name, acquisition_cost, residual_value, accumulated_depreciation,"
            " useful_life_months, status, capitalization_date, last_depreciated_period,"
            " CAST(acquisition_cost AS NUMERIC) - CAST(accumulated_depreciation AS NUMERIC)"
            "  AS net_book_value"
            " FROM fixed_assets ORDER BY name"
        )


class CommercialObligationQueryService(FinanceQueryServiceBase):
    def open_obligations(self, *, instrument_type: str | None = None) -> list[dict]:
        conditions = ["status IN ('OPEN','PARTIALLY_REDEEMED','PENDING_RECOGNITION')"]
        params: list = []
        if instrument_type:
            conditions.append("instrument_type = ?")
            params.append(instrument_type)
        return self._query(
            "SELECT id, instrument_type, source_module, source_instrument_id,"
            " recognition_basis, customer_id, branch_id, original_amount,"
            " recognized_amount, redeemed_amount, released_amount, status,"
            " issued_at, expires_at,"
            " CAST(recognized_amount AS NUMERIC) - CAST(redeemed_amount AS NUMERIC)"
            "  - CAST(released_amount AS NUMERIC) AS outstanding"
            " FROM commercial_obligations"
            f" WHERE {' AND '.join(conditions)} ORDER BY issued_at",
            tuple(params),
        )

    def summary_by_instrument(self) -> list[dict]:
        """Reporte §18: emitido vs canjeado vs expirado vs pendiente por tipo."""
        return self._query(
            "SELECT instrument_type,"
            " COUNT(*) AS instruments,"
            " SUM(CAST(recognized_amount AS NUMERIC)) AS recognized,"
            " SUM(CAST(redeemed_amount AS NUMERIC)) AS redeemed,"
            " SUM(CAST(released_amount AS NUMERIC)) AS released,"
            " SUM(CAST(recognized_amount AS NUMERIC) - CAST(redeemed_amount AS NUMERIC)"
            "   - CAST(released_amount AS NUMERIC)) AS outstanding"
            " FROM commercial_obligations GROUP BY instrument_type ORDER BY instrument_type"
        )

    def expired_without_posting(self) -> list[dict]:
        """Obligaciones vencidas por fecha que siguen abiertas (excepciones)."""
        return self._query(
            "SELECT id, instrument_type, source_instrument_id, expires_at, status"
            " FROM commercial_obligations"
            " WHERE expires_at IS NOT NULL AND expires_at < datetime('now')"
            " AND status IN ('OPEN','PARTIALLY_REDEEMED','PENDING_RECOGNITION')"
        )

    def posting_profiles(self) -> list[dict]:
        return self._query(
            "SELECT id, profile_key, description, instrument_type, effective_from,"
            " effective_to, branch_id, funding_party, active"
            " FROM posting_profiles ORDER BY profile_key, effective_from"
        )

    def events_without_entry(self) -> list[dict]:
        return self._query(
            "SELECT event_id, event_name, operation_id, processed_at"
            " FROM finance_processed_events"
            " WHERE operation_id NOT IN (SELECT operation_id FROM journal_entries)"
            " AND event_name NOT LIKE 'FISCAL_PERIOD%'"
        )


class FinanceDashboardQueryService(FinanceQueryServiceBase):
    """Headline KPIs for the finance overview page (facts only, no forecast)."""

    def overview(self, *, month_from: str, month_to: str) -> dict:
        posted = "('POSTED','REVERSED')"

        def _type_balance(account_types: str, natural_debit: bool) -> str:
            sign = ("CAST(jl.debit_amount AS NUMERIC) - CAST(jl.credit_amount AS NUMERIC)"
                    if natural_debit else
                    "CAST(jl.credit_amount AS NUMERIC) - CAST(jl.debit_amount AS NUMERIC)")
            return self._scalar(
                f"SELECT COALESCE(SUM({sign}), 0) FROM journal_lines jl"
                " JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " JOIN accounts a ON a.id = jl.account_id"
                f" WHERE je.status IN {posted} AND a.account_type IN ({account_types})"
                " AND je.entry_date BETWEEN ? AND ?",
                (month_from, month_to),
            )

        receivables = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM receivables"
            " WHERE status IN ('OPEN','PARTIALLY_COLLECTED')")
        payables = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE status IN ('OPEN','SCHEDULED','PARTIALLY_PAID')")
        obligations = self._scalar(
            "SELECT COALESCE(SUM(CAST(recognized_amount AS NUMERIC)"
            " - CAST(redeemed_amount AS NUMERIC) - CAST(released_amount AS NUMERIC)),0)"
            " FROM commercial_obligations WHERE status IN"
            " ('OPEN','PARTIALLY_REDEEMED','PENDING_RECOGNITION')")
        return {
            "revenue": _type_balance("'REVENUE'", natural_debit=False),
            "contra_revenue": _type_balance("'CONTRA_REVENUE'", natural_debit=True),
            "cost_of_sales": _type_balance("'COST_OF_SALES'", natural_debit=True),
            "expenses": _type_balance("'EXPENSE','OTHER_EXPENSE'", natural_debit=True),
            "other_income": _type_balance("'OTHER_INCOME'", natural_debit=False),
            "open_receivables": receivables,
            "open_payables": payables,
            "open_commercial_obligations": obligations,
        }

    def branch_results(self, *, date_from: str, date_to: str) -> list[dict]:
        """BranchFinancialResultQueryService rows for BI."""
        return self._query(
            "SELECT je.branch_id,"
            " SUM(CASE WHEN a.account_type='REVENUE' THEN"
            "  CAST(jl.credit_amount AS NUMERIC) - CAST(jl.debit_amount AS NUMERIC)"
            "  ELSE 0 END) AS revenue,"
            " SUM(CASE WHEN a.account_type IN ('COST_OF_SALES','EXPENSE','OTHER_EXPENSE',"
            " 'CONTRA_REVENUE') THEN"
            "  CAST(jl.debit_amount AS NUMERIC) - CAST(jl.credit_amount AS NUMERIC)"
            "  ELSE 0 END) AS costs_and_expenses"
            " FROM journal_lines jl"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " JOIN accounts a ON a.id = jl.account_id"
            " WHERE je.status IN ('POSTED','REVERSED') AND je.entry_date BETWEEN ? AND ?"
            " GROUP BY je.branch_id",
            (date_from, date_to),
        )

    def cost_center_actuals(self, *, date_from: str, date_to: str) -> list[dict]:
        """CostCenterActualsQueryService rows for BI."""
        return self._query(
            "SELECT jl.cost_center_id,"
            " SUM(CAST(jl.debit_amount AS NUMERIC) - CAST(jl.credit_amount AS NUMERIC)) AS actuals"
            " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " JOIN accounts a ON a.id = jl.account_id"
            " WHERE je.status IN ('POSTED','REVERSED')"
            " AND a.account_type IN ('EXPENSE','COST_OF_SALES','OTHER_EXPENSE')"
            " AND je.entry_date BETWEEN ? AND ? AND jl.cost_center_id IS NOT NULL"
            " GROUP BY jl.cost_center_id",
            (date_from, date_to),
        )
