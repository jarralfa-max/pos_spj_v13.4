"""PayableQueryService — CxP, pagos y su autorización, anticipos (§12)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.application.finance.ports import PartyDirectoryPort
from backend.application.queries.finance.base_finance_query_service import (
    FinanceQueryServiceBase,
    decimal_sum,
    money_text,
)
from backend.domain.finance.enums import OPEN_PAYABLE_STATUSES, sql_in

_OPEN = sql_in(OPEN_PAYABLE_STATUSES)


class PayableQueryService(FinanceQueryServiceBase):
    def __init__(self, connection, suppliers: PartyDirectoryPort | None = None) -> None:
        """``suppliers`` sólo aporta nombres visibles; sin él las filas no los llevan."""
        super().__init__(connection)
        self._suppliers = suppliers

    def _with_names(self, rows: list[dict]) -> list[dict]:
        names = (self._suppliers.display_names([r["supplier_id"] for r in rows])
                 if self._suppliers is not None else {})
        for row in rows:
            row["supplier_name"] = names.get(row["supplier_id"], "")
        return rows

    def open_payables(self, *, supplier_id: str | None = None, search: str | None = None,
                      blocked_only: bool = False, limit: int = 500,
                      offset: int = 0) -> list[dict]:
        conditions, params = [f"p.status IN {_OPEN}"], []
        if supplier_id:
            conditions.append("p.supplier_id = ?")
            params.append(supplier_id)
        if search:
            conditions.append("fd.document_number LIKE ?")
            params.append(f"%{search}%")
        if blocked_only:
            conditions.append("p.blocked = 1")
        params.extend([limit, offset])
        return self._with_names(self._query(
            "SELECT p.id, p.supplier_id, fd.document_number, p.original_amount,"
            " p.outstanding_amount, p.currency_code, p.issue_date, p.due_date, p.status,"
            " p.branch_id, p.priority, p.payment_terms, p.blocked, p.block_reason,"
            " p.dispute_reason, p.retention_amount, p.early_payment_discount_percent,"
            " p.early_payment_discount_until"
            " FROM payables p JOIN financial_documents fd ON fd.id = p.financial_document_id"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY CASE p.priority WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1"
            " WHEN 'NORMAL' THEN 2 ELSE 3 END, COALESCE(p.due_date, p.issue_date)"
            " LIMIT ? OFFSET ?", tuple(params)))

    def recognized_for_sources(self, source_module: str, source_ids) -> Decimal:
        """Importe ORIGINAL de las CxP ya reconocidas para esos documentos de
        origen. Lo usa Compras para no contar dos veces una compra comprometida."""
        ids = [str(i) for i in source_ids if i]
        if not ids:
            return Decimal("0")
        marks = ",".join("?" for _ in ids)
        rows = self._query(
            "SELECT fd.total_amount FROM financial_documents fd JOIN payables p"
            " ON p.financial_document_id = fd.id WHERE fd.source_module = ?"
            f" AND fd.source_document_id IN ({marks}) AND p.status <> 'CANCELLED'",
            (source_module, *ids))
        return decimal_sum(row["total_amount"] for row in rows)

    def payments(self, *, status: str | None = None, limit: int = 200) -> list[dict]:
        sql = ("SELECT sp.id, sp.payable_id, sp.supplier_id, sp.amount, sp.discount_amount,"
               " sp.scheduled_date, sp.status, sp.scheduled_by, sp.authorized_by,"
               " sp.second_authorization_required, sp.second_authorized_by, sp.executed_by,"
               " sp.executed_date, sp.execution_reference, sp.reference,"
               " ta.name AS treasury_account_name, fd.document_number"
               " FROM supplier_payments sp JOIN payables p ON p.id = sp.payable_id"
               " JOIN financial_documents fd ON fd.id = p.financial_document_id"
               " LEFT JOIN treasury_accounts ta ON ta.id = sp.treasury_account_id")
        params: tuple = ()
        if status:
            sql += " WHERE sp.status = ?"
            params = (status,)
        rows = self._query(sql + " ORDER BY sp.scheduled_date DESC LIMIT ?", params + (limit,))
        for row in rows:
            row["awaiting_second_authorization"] = bool(
                row["second_authorization_required"] and row["authorized_by"]
                and not row["second_authorized_by"] and row["status"] == "SCHEDULED")
        return self._with_names(rows)

    def upcoming_payments(self, *, as_of: str, days: int) -> list[dict]:
        """CxP abiertas que vencen dentro de ``days`` días (o ya vencidas)."""
        limit_date = (date.fromisoformat(as_of) + timedelta(days=days)).isoformat()
        return self._with_names(self._query(
            "SELECT p.id, p.supplier_id, fd.document_number, p.outstanding_amount, p.due_date,"
            " p.status, p.priority FROM payables p"
            " JOIN financial_documents fd ON fd.id = p.financial_document_id"
            f" WHERE p.status IN {_OPEN} AND p.due_date IS NOT NULL AND p.due_date <= ?"
            " ORDER BY p.due_date", (limit_date,)))

    def aging(self, as_of: str) -> list[dict]:
        cut = date.fromisoformat(as_of)
        buckets = {name: [] for name in ("CURRENT", "1-30", "31-60", "61-90", "90+",
                                         "NO_DUE_DATE")}
        for row in self._query(f"SELECT outstanding_amount, due_date FROM payables"
                               f" WHERE status IN {_OPEN}"):
            if not row["due_date"]:
                key = "NO_DUE_DATE"
            else:
                days = (cut - date.fromisoformat(row["due_date"][:10])).days
                key = ("CURRENT" if days <= 0 else "1-30" if days <= 30 else
                       "31-60" if days <= 60 else "61-90" if days <= 90 else "90+")
            buckets[key].append(row["outstanding_amount"])
        return [{"bucket": k, "amount": money_text(decimal_sum(v)), "documents": len(v)}
                for k, v in buckets.items()]

    def supplier_advances(self, *, supplier_id: str | None = None) -> list[dict]:
        sql = ("SELECT id, supplier_id, advance_date, reference, amount, applied_amount,"
               " status FROM supplier_advances WHERE status IN ('OPEN','PARTIALLY_APPLIED')")
        params: tuple = ()
        if supplier_id:
            sql += " AND supplier_id=?"
            params = (supplier_id,)
        rows = self._query(sql + " ORDER BY advance_date", params)
        for row in rows:
            row["available"] = money_text(decimal_sum([row["amount"]])
                                          - decimal_sum([row["applied_amount"]]))
        return self._with_names(rows)

    def search_suppliers(self, text: str, limit: int = 20) -> list[dict]:
        return self._suppliers.search(text, limit) if self._suppliers is not None else []
