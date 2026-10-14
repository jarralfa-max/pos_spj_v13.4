"""Canonical read-only query services for the finance bounded context.

Consumers: desktop UI pages and BI (read-only, §21). BI never writes to the
ledger and never queries finance tables directly — it goes through these
services and their stable row shapes.
"""

from __future__ import annotations

from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
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
    def _entry_filters(self, *, status, journal_type, date_from, date_to, search):
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
        if search:
            conditions.append("(je.entry_number LIKE ? OR je.description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        return conditions, params

    def list_entries(self, *, status: str | None = None, journal_type: str | None = None,
                     date_from: str | None = None, date_to: str | None = None,
                     search: str | None = None,
                     limit: int = 200, offset: int = 0) -> list[dict]:
        """Página de asientos (auditoría F24: con ``offset`` y ``count_entries``
        los más de 200 siguen siendo accesibles)."""
        conditions, params = self._entry_filters(
            status=status, journal_type=journal_type, date_from=date_from,
            date_to=date_to, search=search)
        params.extend([limit, offset])
        rows = self._query(
            "SELECT je.id, je.entry_number, je.entry_date, je.description, je.status,"
            " j.journal_type, je.source_module, je.posting_purpose, je.branch_id,"
            " je.currency_code, je.reversal_of_entry_id, je.reversed_by_entry_id"
            " FROM journal_entries je JOIN journals j ON j.id = je.journal_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY je.entry_date DESC, je.entry_number DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
        for row in rows:
            row["total"] = format(decimal_sum(
                r[0] for r in self._conn.execute(
                    "SELECT debit_amount FROM journal_lines WHERE journal_entry_id = ?",
                    (row["id"],)).fetchall()), "f")
        return rows

    def count_entries(self, *, status: str | None = None, journal_type: str | None = None,
                      date_from: str | None = None, date_to: str | None = None,
                      search: str | None = None) -> int:
        conditions, params = self._entry_filters(
            status=status, journal_type=journal_type, date_from=date_from,
            date_to=date_to, search=search)
        return int(self._scalar(
            "SELECT COUNT(*) FROM journal_entries je JOIN journals j ON j.id = je.journal_id"
            f" WHERE {' AND '.join(conditions)}", tuple(params)))

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
            "  WHEN r.due_date IS NULL THEN 'NO_DUE_DATE'"
            "  WHEN r.due_date >= ? THEN 'CURRENT'"
            "  WHEN julianday(?) - julianday(r.due_date) <= 30 THEN '1-30'"
            "  WHEN julianday(?) - julianday(r.due_date) <= 60 THEN '31-60'"
            "  WHEN julianday(?) - julianday(r.due_date) <= 90 THEN '61-90'"
            "  ELSE '90+'"
            " END AS bucket"
            " FROM receivables r WHERE r.status IN ('OPEN','PARTIALLY_COLLECTED')",
            (as_of, as_of, as_of, as_of),
        )

    def customer_display_names(self) -> dict[str, str]:
        """Nombre visible de los clientes con CxC (F24): maestro canónico
        (``customers``) y, si existe, el catálogo anterior (``clientes``).
        Sólo lectura; sin maestro devuelve vacío y la UI muestra el id."""
        ids = [r["customer_id"] for r in self._query(
            "SELECT DISTINCT customer_id FROM receivables")]
        if not ids:
            return {}
        names: dict[str, str] = {}
        tables = {r["name"] for r in self._query(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name IN ('customers','clientes')")}
        placeholders = ",".join("?" for _ in ids)
        if "clientes" in tables:
            for row in self._query(
                    f"SELECT CAST(id AS TEXT) AS id, nombre FROM clientes"
                    f" WHERE CAST(id AS TEXT) IN ({placeholders})", tuple(ids)):
                names[row["id"]] = row["nombre"]
        if "customers" in tables:
            for row in self._query(
                    f"SELECT id, display_name FROM customers WHERE id IN ({placeholders})",
                    tuple(ids)):
                if row["display_name"]:
                    names[row["id"]] = row["display_name"]
        return names

    def collection_history(self, *, customer_id: str | None = None,
                           date_from: str | None = None, date_to: str | None = None,
                           search: str | None = None,
                           limit: int = 200, offset: int = 0) -> list[dict]:
        """Historial de COBROS (auditoría F23): cada cobro registrado, también
        los de facturas ya liquidadas — antes la pantalla «Cobros» mostraba la
        deuda abierta y un cobro desaparecía al saldarse su factura."""
        conditions = ["1=1"]
        params: list = []
        if customer_id:
            conditions.append("c.customer_id = ?")
            params.append(customer_id)
        if date_from:
            conditions.append("c.collection_date >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("c.collection_date <= ?")
            params.append(date_to)
        if search:
            conditions.append("(fd.document_number LIKE ? OR c.reference LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        params.extend([limit, offset])
        return self._query(
            "SELECT c.id, c.collection_date, c.reference, fd.document_number,"
            " c.customer_id, c.amount, c.currency_code, ta.name AS treasury_account_name,"
            " c.journal_entry_id, je.entry_number, je.status AS entry_status,"
            " r.status AS receivable_status"
            " FROM collections c"
            " JOIN receivables r ON r.id = c.receivable_id"
            " JOIN financial_documents fd ON fd.id = r.financial_document_id"
            " LEFT JOIN treasury_accounts ta ON ta.id = c.treasury_account_id"
            " LEFT JOIN journal_entries je ON je.id = c.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY c.collection_date DESC, c.created_at DESC LIMIT ? OFFSET ?",
            tuple(params))

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
        """Saldo por cuenta de tesorería desde su espejo contable.

        Auditoría F05: sólo cuentan asientos CONTABILIZADOS de la moneda de la
        cuenta (antes el filtro de estado estaba en el LEFT JOIN y un borrador
        de 100 aparecía como saldo bancario). Si dos cuentas comparten el mismo
        espejo, el mayor no distingue a cuál pertenece cada movimiento: esas
        filas se marcan ``shared_mirror`` y su saldo es el COLECTIVO, que
        ``treasury_total`` cuenta una sola vez."""
        accounts = self._query(
            "SELECT ta.id, ta.name, ta.account_type, ta.currency_code, ta.branch_id,"
            " ta.ledger_account_id FROM treasury_accounts ta WHERE ta.active = 1"
            " ORDER BY ta.name")
        sharing: dict[str, int] = {}
        for account in accounts:
            sharing[account["ledger_account_id"]] = sharing.get(account["ledger_account_id"], 0) + 1
        for account in accounts:
            account["balance"] = format(self._mirror_balance(
                account["ledger_account_id"], account["currency_code"]), "f")
            account["shared_mirror"] = sharing[account["ledger_account_id"]] > 1
        return accounts

    def _mirror_balance(self, ledger_account_id: str, currency_code: str):
        rows = self._conn.execute(
            "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
            " JOIN journal_entries je ON je.id = jl.journal_entry_id"
            " WHERE jl.account_id = ? AND je.status IN ('POSTED','REVERSED')"
            " AND je.currency_code = ?", (ledger_account_id, currency_code)).fetchall()
        return decimal_sum(r[0] for r in rows) - decimal_sum(r[1] for r in rows)

    def treasury_total(self) -> dict[str, str]:
        """Total por moneda contando cada espejo UNA vez (cuadra con el mayor)."""
        seen: set[tuple[str, str]] = set()
        totals: dict[str, object] = {}
        for account in self.treasury_position():
            key = (account["ledger_account_id"], account["currency_code"])
            if key in seen:
                continue
            seen.add(key)
            totals[account["currency_code"]] = decimal_sum(
                [totals.get(account["currency_code"], 0), account["balance"]])
        return {currency: format(total, "f") for currency, total in totals.items()}

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
        rows = self._query(
            "SELECT b.id AS budget_id, b.name, b.status, bl.period_code,"
            " a.code AS account_code, a.name AS account_name,"
            " bl.planned_amount, bl.committed_amount, bl.accrued_amount"
            " FROM budgets b JOIN budget_lines bl ON bl.budget_id = b.id"
            " JOIN accounts a ON a.id = bl.account_id"
            " WHERE b.fiscal_year = ? AND b.status = 'APPROVED'"
            " ORDER BY bl.period_code, a.code",
            (fiscal_year,),
        )
        for row in rows:
            row["available"] = format(
                decimal_sum([row["planned_amount"]]) - decimal_sum([row["committed_amount"]])
                - decimal_sum([row["accrued_amount"]]), "f")
        return rows

    def list_budgets(self) -> list[dict]:
        return self._query(
            "SELECT id, name, fiscal_year, version, status, approved_by, approved_at"
            " FROM budgets ORDER BY fiscal_year DESC, version DESC"
        )


class FixedAssetQueryService(FinanceQueryServiceBase):
    def list_assets(self) -> list[dict]:
        rows = self._query(
            "SELECT id, name, acquisition_cost, residual_value, accumulated_depreciation,"
            " useful_life_months, status, capitalization_date, last_depreciated_period"
            " FROM fixed_assets ORDER BY name"
        )
        for row in rows:
            row["net_book_value"] = format(decimal_sum([row["acquisition_cost"]])
                                           - decimal_sum([row["accumulated_depreciation"]]), "f")
        return rows


class CommercialObligationQueryService(FinanceQueryServiceBase):
    def open_obligations(self, *, instrument_type: str | None = None) -> list[dict]:
        conditions = ["status IN ('OPEN','PARTIALLY_REDEEMED','PENDING_RECOGNITION')"]
        params: list = []
        if instrument_type:
            conditions.append("instrument_type = ?")
            params.append(instrument_type)
        rows = self._query(
            "SELECT id, instrument_type, source_module, source_instrument_id,"
            " recognition_basis, customer_id, branch_id, original_amount,"
            " recognized_amount, redeemed_amount, released_amount, status,"
            " issued_at, expires_at"
            " FROM commercial_obligations"
            f" WHERE {' AND '.join(conditions)} ORDER BY issued_at",
            tuple(params),
        )
        for row in rows:
            row["outstanding"] = format(self._outstanding(row), "f")
        return rows

    @staticmethod
    def _outstanding(row: dict):
        return (decimal_sum([row["recognized_amount"]]) - decimal_sum([row["redeemed_amount"]])
                - decimal_sum([row["released_amount"]]))

    def summary_by_instrument(self) -> list[dict]:
        """Reporte §18: emitido vs canjeado vs expirado vs pendiente por tipo."""
        grouped: dict[str, dict] = {}
        for row in self._query(
                "SELECT instrument_type, recognized_amount, redeemed_amount, released_amount"
                " FROM commercial_obligations ORDER BY instrument_type"):
            bucket = grouped.setdefault(row["instrument_type"], {
                "instrument_type": row["instrument_type"], "instruments": 0,
                "recognized": [], "redeemed": [], "released": [], "outstanding": []})
            bucket["instruments"] += 1
            for key, column in (("recognized", "recognized_amount"),
                                ("redeemed", "redeemed_amount"),
                                ("released", "released_amount")):
                bucket[key].append(row[column])
            bucket["outstanding"].append(self._outstanding(row))
        return [{**b, **{k: format(decimal_sum(b[k]), "f")
                         for k in ("recognized", "redeemed", "released", "outstanding")}}
                for b in grouped.values()]

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
            rows = self._conn.execute(
                "SELECT jl.debit_amount, jl.credit_amount FROM journal_lines jl"
                " JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " JOIN accounts a ON a.id = jl.account_id"
                f" WHERE je.status IN {posted} AND a.account_type IN ({account_types})"
                " AND je.entry_date BETWEEN ? AND ? AND je.currency_code = 'MXN'",
                (month_from, month_to),
            ).fetchall()
            debits = decimal_sum(r[0] for r in rows)
            credits = decimal_sum(r[1] for r in rows)
            return format(debits - credits if natural_debit else credits - debits, "f")

        receivables = self._money_sum(
            "SELECT outstanding_amount FROM receivables"
            " WHERE status IN ('OPEN','PARTIALLY_COLLECTED')")
        payables = self._money_sum(
            "SELECT outstanding_amount FROM payables"
            " WHERE status IN ('OPEN','SCHEDULED','PARTIALLY_PAID')")
        obligations = format(sum(
            (CommercialObligationQueryService._outstanding(r) for r in self._query(
                "SELECT recognized_amount, redeemed_amount, released_amount"
                " FROM commercial_obligations WHERE status IN"
                " ('OPEN','PARTIALLY_REDEEMED','PENDING_RECOGNITION')")),
            decimal_sum([])), "f")
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
        """BranchFinancialResultQueryService rows for BI (sumas exactas, F20)."""
        grouped: dict = {}
        for row in self._query(
                "SELECT je.branch_id, a.account_type, jl.debit_amount, jl.credit_amount"
                " FROM journal_lines jl"
                " JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " JOIN accounts a ON a.id = jl.account_id"
                " WHERE je.status IN ('POSTED','REVERSED') AND je.entry_date BETWEEN ? AND ?",
                (date_from, date_to)):
            bucket = grouped.setdefault(row["branch_id"], {"revenue": decimal_sum([]),
                                                           "costs": decimal_sum([])})
            delta = decimal_sum([row["debit_amount"]]) - decimal_sum([row["credit_amount"]])
            if row["account_type"] == "REVENUE":
                bucket["revenue"] -= delta
            elif row["account_type"] in ("COST_OF_SALES", "EXPENSE", "OTHER_EXPENSE",
                                         "CONTRA_REVENUE"):
                bucket["costs"] += delta
        return [{"branch_id": branch, "revenue": format(v["revenue"], "f"),
                 "costs_and_expenses": format(v["costs"], "f")}
                for branch, v in grouped.items()]

    def cost_center_actuals(self, *, date_from: str, date_to: str) -> list[dict]:
        """CostCenterActualsQueryService rows for BI (sumas exactas, F20)."""
        grouped: dict = {}
        for row in self._query(
                "SELECT jl.cost_center_id, jl.debit_amount, jl.credit_amount"
                " FROM journal_lines jl JOIN journal_entries je ON je.id = jl.journal_entry_id"
                " JOIN accounts a ON a.id = jl.account_id"
                " WHERE je.status IN ('POSTED','REVERSED')"
                " AND a.account_type IN ('EXPENSE','COST_OF_SALES','OTHER_EXPENSE')"
                " AND je.entry_date BETWEEN ? AND ? AND jl.cost_center_id IS NOT NULL",
                (date_from, date_to)):
            grouped[row["cost_center_id"]] = grouped.get(row["cost_center_id"], decimal_sum([]))                 + decimal_sum([row["debit_amount"]]) - decimal_sum([row["credit_amount"]])
        return [{"cost_center_id": cc, "actuals": format(total, "f")}
                for cc, total in grouped.items()]
