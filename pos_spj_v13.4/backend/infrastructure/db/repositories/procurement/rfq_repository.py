"""RfqRepository — persists requests for quotation and the supplier quotes that
answer them (header + lines). Awarding a quote is a state flag; comparison logic
lives in the domain/application, never in the widget."""

from __future__ import annotations

import json

from backend.domain.procurement.entities import (
    RequestForQuotation,
    SupplierQuote,
    SupplierQuoteLine,
)
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)


class RfqRepository(ProcurementRepositoryBase):
    def save_rfq(self, rfq: RequestForQuotation) -> None:
        self._execute(
            "INSERT INTO requests_for_quotation (id, document_number, supplier_ids,"
            " response_deadline, status, operation_id, created_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status",
            (rfq.id, rfq.document_number, json.dumps(list(rfq.supplier_ids)),
             rfq.response_deadline.isoformat() if rfq.response_deadline else None,
             rfq.status, None, rfq.created_at))

    def set_rfq_operation_id(self, rfq_id: str, operation_id: str) -> None:
        self._execute("UPDATE requests_for_quotation SET operation_id=? WHERE id=?",
                      (operation_id, rfq_id))

    def get_rfq(self, rfq_id: str) -> RequestForQuotation | None:
        row = self._query_one("SELECT * FROM requests_for_quotation WHERE id=?", (rfq_id,))
        if row is None:
            return None
        return RequestForQuotation(
            id=row["id"], document_number=row["document_number"],
            supplier_ids=tuple(json.loads(row["supplier_ids"])),
            status=row["status"], created_at=row["created_at"])

    def save_quote(self, quote: SupplierQuote) -> None:
        self._execute(
            "INSERT INTO supplier_quotes (id, rfq_id, supplier_id, currency_code,"
            " lead_time_days, total, awarded, created_at) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET total=excluded.total, awarded=excluded.awarded",
            (quote.id, quote.rfq_id, quote.supplier_id, quote.currency_code,
             quote.lead_time_days, dec_str(quote.total().amount),
             1 if quote.awarded else 0, quote.created_at))
        self._execute("DELETE FROM supplier_quote_lines WHERE quote_id=?", (quote.id,))
        for ln in quote.lines:
            self._execute(
                "INSERT INTO supplier_quote_lines (id, quote_id, product_id, quantity,"
                " unit_price, currency_code) VALUES (?,?,?,?,?,?)",
                (ln.id, quote.id, ln.product_id, dec_str(ln.quantity),
                 dec_str(ln.unit_price.amount), ln.unit_price.currency_code))

    def get_quote(self, quote_id: str) -> SupplierQuote | None:
        row = self._query_one("SELECT * FROM supplier_quotes WHERE id=?", (quote_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT * FROM supplier_quote_lines WHERE quote_id=? ORDER BY id", (quote_id,))
        lines = [
            SupplierQuoteLine(
                id=lr["id"], product_id=lr["product_id"], quantity=to_decimal(lr["quantity"]),
                unit_price=Money(to_decimal(lr["unit_price"]), lr["currency_code"]))
            for lr in line_rows
        ]
        return SupplierQuote(
            id=row["id"], rfq_id=row["rfq_id"], supplier_id=row["supplier_id"],
            currency_code=row["currency_code"], lead_time_days=row["lead_time_days"],
            lines=lines, awarded=bool(row["awarded"]), created_at=row["created_at"])

    def list_quotes_for_rfq(self, rfq_id: str) -> list[SupplierQuote]:
        rows = self._query("SELECT id FROM supplier_quotes WHERE rfq_id=? ORDER BY created_at",
                           (rfq_id,))
        return [self.get_quote(r["id"]) for r in rows]
