"""ReceivableQueryService — CxC, cobros, aplicaciones, saldo a favor, antigüedad (§11)."""

from __future__ import annotations

from datetime import date

from backend.application.finance.ports import PartyDirectoryPort
from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)
from backend.domain.finance.enums import OPEN_RECEIVABLE_STATUSES, sql_in
from backend.domain.finance.services.receivable_service import AGING_BUCKETS

_OPEN = sql_in(OPEN_RECEIVABLE_STATUSES)


def _bucket(due_date: str | None, as_of: date) -> str:
    if not due_date:
        return "NO_DUE_DATE"
    days = (as_of - date.fromisoformat(due_date[:10])).days
    if days <= 0:
        return "CURRENT"
    if days <= 30:
        return "1-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


class ReceivableQueryService(FinanceQueryServiceBase):
    def __init__(self, connection, customers: PartyDirectoryPort | None = None) -> None:
        """``customers`` sólo aporta nombres visibles; sin él las filas no los llevan."""
        super().__init__(connection)
        self._customers = customers

    def _with_names(self, rows: list[dict]) -> list[dict]:
        names = (self._customers.display_names([r["customer_id"] for r in rows])
                 if self._customers is not None else {})
        for row in rows:
            row["customer_name"] = names.get(row["customer_id"], "")
        return rows

    def open_receivables(self, *, customer_id: str | None = None, search: str | None = None,
                         status: str | None = None, limit: int = 500,
                         offset: int = 0) -> list[dict]:
        conditions, params = [f"r.status IN {_OPEN}"], []
        if customer_id:
            conditions.append("r.customer_id = ?")
            params.append(customer_id)
        if status:
            conditions.append("r.status = ?")
            params.append(status)
        if search:
            conditions.append("fd.document_number LIKE ?")
            params.append(f"%{search}%")
        params.extend([limit, offset])
        return self._with_names(self._query(
            "SELECT r.id, r.customer_id, fd.document_number, r.original_amount,"
            " r.outstanding_amount, r.currency_code, r.issue_date, r.due_date, r.status,"
            " r.branch_id, r.dispute_reason, r.credit_term_days"
            " FROM receivables r JOIN financial_documents fd ON fd.id = r.financial_document_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY COALESCE(r.due_date, r.issue_date), r.issue_date LIMIT ? OFFSET ?",
            tuple(params)))

    def count_open(self, *, customer_id: str | None = None) -> int:
        if customer_id:
            return int(self._scalar(f"SELECT COUNT(*) FROM receivables WHERE status IN {_OPEN}"
                                    " AND customer_id=?", (customer_id,)))
        return int(self._scalar(f"SELECT COUNT(*) FROM receivables WHERE status IN {_OPEN}"))

    def aging(self, as_of: str) -> list[dict]:
        cut = date.fromisoformat(as_of)
        rows = self._query(
            "SELECT r.id, r.customer_id, r.outstanding_amount, r.due_date"
            f" FROM receivables r WHERE r.status IN {_OPEN}")
        for row in rows:
            row["bucket"] = _bucket(row["due_date"], cut)
        return self._with_names(rows)

    def aging_summary(self, as_of: str) -> list[dict]:
        """Total por cubeta de antigüedad (orden fijo del dominio)."""
        buckets: dict[str, list] = {name: [] for name in AGING_BUCKETS}
        for row in self.aging(as_of):
            buckets[row["bucket"]].append(row["outstanding_amount"])
        return [{"bucket": name, "amount": money_text(decimal_sum(values)),
                 "documents": len(values)} for name, values in buckets.items()]

    def customer_display_names(self) -> dict[str, str]:
        ids = [r["customer_id"] for r in self._query(
            "SELECT DISTINCT customer_id FROM receivables")]
        return self._customers.display_names(ids) if self._customers is not None else {}

    def collection_history(self, *, customer_id: str | None = None,
                           date_from: str | None = None, date_to: str | None = None,
                           search: str | None = None,
                           limit: int = 200, offset: int = 0) -> list[dict]:
        """Historial de COBROS (F23) con lo aplicado y lo que quedó a favor."""
        conditions, params = ["1=1"], []
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
            conditions.append("c.reference LIKE ?")
            params.append(f"%{search}%")
        params.extend([limit, offset])
        rows = self._query(
            "SELECT c.id, c.collection_date, c.reference, c.customer_id, c.amount,"
            " c.applied_amount, c.currency_code, c.status, c.payment_method,"
            " ta.name AS treasury_account_name, c.journal_entry_id, je.entry_number,"
            " je.status AS entry_status"
            " FROM collections c"
            " LEFT JOIN treasury_accounts ta ON ta.id = c.treasury_account_id"
            " LEFT JOIN journal_entries je ON je.id = c.journal_entry_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY c.collection_date DESC, c.created_at DESC LIMIT ? OFFSET ?",
            tuple(params))
        for row in rows:
            row["unapplied"] = money_text(decimal_sum([row["amount"]])
                                          - decimal_sum([row["applied_amount"]]))
        return self._with_names(rows)

    def applications(self, *, receivable_id: str | None = None,
                     collection_id: str | None = None) -> list[dict]:
        column, value = (("a.receivable_id", receivable_id) if receivable_id
                         else ("a.collection_id", collection_id))
        return self._query(
            "SELECT a.id, a.collection_id, a.receivable_id, a.applied_amount, a.created_at,"
            " fd.document_number, c.reference AS collection_reference, c.collection_date"
            " FROM collection_applications a JOIN collections c ON c.id = a.collection_id"
            " JOIN receivables r ON r.id = a.receivable_id"
            " JOIN financial_documents fd ON fd.id = r.financial_document_id"
            f" WHERE {column} = ? ORDER BY a.created_at", (value,))

    def collections_by_receivable(self, receivable_id: str) -> list[dict]:
        return self.applications(receivable_id=receivable_id)

    def customer_credit_balances(self, *, customer_id: str | None = None) -> list[dict]:
        """Saldo a favor (anticipos): lo no aplicado de cobros abiertos."""
        sql = ("SELECT id, customer_id, collection_date, reference, amount, applied_amount,"
               " currency_code FROM collections WHERE status IN ('UNAPPLIED','PARTIALLY_APPLIED')")
        params: tuple = ()
        if customer_id:
            sql += " AND customer_id = ?"
            params = (customer_id,)
        rows = self._query(sql + " ORDER BY collection_date", params)
        for row in rows:
            row["available"] = money_text(decimal_sum([row["amount"]])
                                          - decimal_sum([row["applied_amount"]]))
        return self._with_names(rows)

    def payment_promises(self, receivable_id: str) -> list[dict]:
        return self._query(
            "SELECT id, promised_date, promised_amount, note, status, created_by"
            " FROM receivable_payment_promises WHERE receivable_id=? ORDER BY promised_date",
            (receivable_id,))

    def search_customers(self, text: str, limit: int = 20) -> list[dict]:
        return self._customers.search(text, limit) if self._customers is not None else []
