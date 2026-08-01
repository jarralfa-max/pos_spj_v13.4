"""RfqRepository — persists requests for quotation and the supplier quotes that
answer them (header + lines). Awarding a quote is a state flag; comparison logic
lives in the domain/application, never in the widget."""

from __future__ import annotations

from backend.domain.procurement.entities import (
    PurchaseAward,
    PurchaseAwardLine,
    RequestForQuotation,
    RfqSupplierInvitation,
    SupplierQuote,
    SupplierQuoteLine,
)
from backend.domain.procurement.enums import PurchaseNature
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    to_decimal,
)


class RfqRepository(ProcurementRepositoryBase):
    def save_rfq(self, rfq: RequestForQuotation) -> None:
        self._execute(
            "INSERT INTO requests_for_quotation (id, document_number, requisition_id,"
            " response_deadline, status, operation_id, created_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status",
            (rfq.id, rfq.document_number, rfq.requisition_id,
             rfq.response_deadline.isoformat() if rfq.response_deadline else None,
             rfq.status, None, rfq.created_at))
        for invitation in rfq.invitations:
            self._execute(
                "INSERT INTO rfq_supplier_invitations"
                " (id,rfq_id,supplier_id,status,invited_at) VALUES (?,?,?,?,?)"
                " ON CONFLICT(rfq_id,supplier_id) DO UPDATE SET status=excluded.status",
                (invitation.id, invitation.rfq_id, invitation.supplier_id,
                 invitation.status, invitation.invited_at))

    def set_rfq_operation_id(self, rfq_id: str, operation_id: str) -> None:
        self._execute("UPDATE requests_for_quotation SET operation_id=? WHERE id=?",
                      (operation_id, rfq_id))

    def get_rfq(self, rfq_id: str) -> RequestForQuotation | None:
        row = self._query_one("SELECT * FROM requests_for_quotation WHERE id=?", (rfq_id,))
        if row is None:
            return None
        invitations = [RfqSupplierInvitation(**inv) for inv in self._query(
            "SELECT id,rfq_id,supplier_id,status,invited_at"
            " FROM rfq_supplier_invitations WHERE rfq_id=? ORDER BY invited_at", (rfq_id,))]
        return RequestForQuotation(
            id=row["id"], document_number=row["document_number"],
            invitations=invitations, requisition_id=row["requisition_id"],
            status=row["status"], created_at=row["created_at"])

    def save_quote(self, quote: SupplierQuote) -> None:
        self._execute(
            "INSERT INTO supplier_quotes (id, rfq_id, supplier_id, currency_code,"
            " lead_time_days, total, operation_id, created_at) VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET total=excluded.total",
            (quote.id, quote.rfq_id, quote.supplier_id, quote.currency_code,
             quote.lead_time_days, dec_str(quote.total().amount), None, quote.created_at))
        self._execute("DELETE FROM supplier_quote_lines WHERE quote_id=?", (quote.id,))
        for ln in quote.lines:
            self._execute(
                "INSERT INTO supplier_quote_lines (id, quote_id, product_id, quantity,"
                " unit_price, purchase_nature, discount, tax, currency_code)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (ln.id, quote.id, ln.product_id, dec_str(ln.quantity),
                 dec_str(ln.unit_price.amount), ln.purchase_nature.value,
                 dec_str(ln.discount.amount if ln.discount else 0),
                 dec_str(ln.tax.amount if ln.tax else 0), ln.unit_price.currency_code))

    def set_quote_operation_id(self, quote_id: str, operation_id: str) -> None:
        self._execute("UPDATE supplier_quotes SET operation_id=? WHERE id=?",
                      (operation_id, quote_id))

    def get_quote_by_operation(self, operation_id: str) -> SupplierQuote | None:
        row = self._query_one("SELECT id FROM supplier_quotes WHERE operation_id=?",
                              (operation_id,))
        return self.get_quote(row["id"]) if row else None

    def get_quote(self, quote_id: str) -> SupplierQuote | None:
        row = self._query_one("SELECT * FROM supplier_quotes WHERE id=?", (quote_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT * FROM supplier_quote_lines WHERE quote_id=? ORDER BY id", (quote_id,))
        lines = [
            SupplierQuoteLine(
                id=lr["id"], product_id=lr["product_id"],
                quantity=to_decimal(lr["quantity"]),
                unit_price=Money(to_decimal(lr["unit_price"]), lr["currency_code"]),
                purchase_nature=PurchaseNature(lr["purchase_nature"]),
                discount=Money(to_decimal(lr["discount"]), lr["currency_code"]),
                tax=Money(to_decimal(lr["tax"]), lr["currency_code"]))
            for lr in line_rows
        ]
        return SupplierQuote(
            id=row["id"], rfq_id=row["rfq_id"], supplier_id=row["supplier_id"],
            currency_code=row["currency_code"], lead_time_days=row["lead_time_days"],
            lines=lines, created_at=row["created_at"])

    def list_quotes_for_rfq(self, rfq_id: str) -> list[SupplierQuote]:
        rows = self._query("SELECT id FROM supplier_quotes WHERE rfq_id=? ORDER BY created_at",
                           (rfq_id,))
        return [self.get_quote(r["id"]) for r in rows]

    def save_award(self, award: PurchaseAward, operation_id: str) -> None:
        self._execute(
            "INSERT INTO purchase_awards"
            " (id,rfq_id,approved_by_user_id,operation_id,created_at) VALUES (?,?,?,?,?)",
            (award.id, award.rfq_id, award.approved_by_user_id, operation_id,
             award.created_at))
        for line in award.lines:
            self._execute(
                "INSERT INTO purchase_award_lines"
                " (id,award_id,quote_line_id,supplier_id,awarded_quantity,justification)"
                " VALUES (?,?,?,?,?,?)",
                (line.id, award.id, line.quote_line_id, line.supplier_id,
                 dec_str(line.awarded_quantity), line.justification))

    def get_award_by_operation(self, operation_id: str) -> PurchaseAward | None:
        row = self._query_one("SELECT * FROM purchase_awards WHERE operation_id=?",
                              (operation_id,))
        if not row:
            return None
        lines = [PurchaseAwardLine(
            id=line["id"], award_id=line["award_id"], quote_line_id=line["quote_line_id"],
            supplier_id=line["supplier_id"],
            awarded_quantity=to_decimal(line["awarded_quantity"]),
            justification=line["justification"])
            for line in self._query(
                "SELECT * FROM purchase_award_lines WHERE award_id=?", (row["id"],))]
        return PurchaseAward(row["id"], row["rfq_id"], row["approved_by_user_id"],
                             lines, row["created_at"])
