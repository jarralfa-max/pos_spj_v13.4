"""SupplierInvoiceRepository — persists supplier invoices and their match records.

UNIQUE(supplier_id, invoice_number) blocks duplicate captures structurally; the
match record keeps who released a variance (segregation lives in the use case)."""

from __future__ import annotations

from decimal import Decimal

from backend.domain.procurement.entities import SupplierInvoice, SupplierInvoiceLine
from backend.domain.procurement.value_objects import Money
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    now_iso,
    to_decimal,
)
from backend.shared.ids import new_uuid


class SupplierInvoiceRepository(ProcurementRepositoryBase):
    def save(self, inv: SupplierInvoice) -> None:
        self._execute(
            "INSERT INTO supplier_invoices (id, document_number, supplier_id,"
            " invoice_number, subtotal, tax_total, total, currency_code, purchase_order_id,"
            " direct_purchase_id, uuid_fiscal, status, match_result, captured_by_user_id,"
            " matched_by_user_id,released_by_user_id,payable_id,operation_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " match_result=excluded.match_result, payable_id=excluded.payable_id",
            (inv.id, inv.document_number, inv.supplier_id, inv.invoice_number,
             dec_str(inv.subtotal.amount if inv.subtotal else 0),
             dec_str(inv.tax_total.amount if inv.tax_total else 0),
             dec_str(inv.total.amount), inv.total.currency_code, inv.purchase_order_id,
             inv.direct_purchase_id, inv.uuid_fiscal, inv.status, inv.match_result,
             inv.captured_by_user_id, inv.matched_by_user_id, inv.released_by_user_id,
             None, None, inv.created_at))
        self._execute("DELETE FROM supplier_invoice_lines WHERE supplier_invoice_id=?",
                      (inv.id,))
        for line in inv.lines:
            self._execute(
                "INSERT INTO supplier_invoice_lines"
                " (id,supplier_invoice_id,product_id,invoiced_quantity,unit_price,tax,"
                " currency_code,purchase_order_line_id,direct_purchase_line_id,receipt_line_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (line.id, inv.id, line.product_id, dec_str(line.invoiced_quantity),
                 dec_str(line.unit_price.amount), dec_str(line.tax.amount),
                 line.unit_price.currency_code, line.purchase_order_line_id,
                 line.direct_purchase_line_id, line.receipt_line_id))

    def set_operation_id(self, invoice_id: str, operation_id: str) -> None:
        self._execute("UPDATE supplier_invoices SET operation_id=? WHERE id=?",
                      (operation_id, invoice_id))

    def link_payable(self, invoice_id: str, payable_id: str) -> None:
        self._execute("UPDATE supplier_invoices SET payable_id=? WHERE id=?",
                      (payable_id, invoice_id))

    def record_match(self, *, invoice_id: str, result: str,
                     released_by_user_id: str | None = None, notes: str = "") -> None:
        self._execute(
            "INSERT INTO supplier_invoice_matches (id, supplier_invoice_id, result,"
            " released_by_user_id, notes, created_at) VALUES (?,?,?,?,?,?)",
            (new_uuid(), invoice_id, result, released_by_user_id, notes, now_iso()))

    def get_by_operation(self, operation_id: str) -> SupplierInvoice | None:
        row = self._query_one("SELECT * FROM supplier_invoices WHERE operation_id=?",
                              (operation_id,))
        return self._hydrate(row) if row else None

    def get(self, invoice_id: str) -> SupplierInvoice | None:
        row = self._query_one("SELECT * FROM supplier_invoices WHERE id=?", (invoice_id,))
        return self._hydrate(row) if row else None

    def exists_for_supplier(self, supplier_id: str, invoice_number: str) -> bool:
        return self._query_one(
            "SELECT id FROM supplier_invoices WHERE supplier_id=? AND invoice_number=?",
            (supplier_id, invoice_number)) is not None

    def previously_invoiced_quantity(self, purchase_order_line_id: str,
                                     excluding_invoice_id: str) -> Decimal:
        rows = self._query(
            "SELECT l.invoiced_quantity FROM supplier_invoice_lines l"
            " JOIN supplier_invoices i ON i.id=l.supplier_invoice_id"
            " WHERE l.purchase_order_line_id=? AND l.supplier_invoice_id<>?"
            " AND i.status<>'CANCELLED'",
            (purchase_order_line_id, excluding_invoice_id))
        return sum((to_decimal(row["invoiced_quantity"]) for row in rows), Decimal("0"))

    def _hydrate(self, row: dict) -> SupplierInvoice:
        lines = [SupplierInvoiceLine(
            id=line["id"], supplier_invoice_id=line["supplier_invoice_id"],
            product_id=line["product_id"],
            invoiced_quantity=to_decimal(line["invoiced_quantity"]),
            unit_price=Money(to_decimal(line["unit_price"]), line["currency_code"]),
            tax=Money(to_decimal(line["tax"]), line["currency_code"]),
            purchase_order_line_id=line["purchase_order_line_id"],
            direct_purchase_line_id=line["direct_purchase_line_id"],
            receipt_line_id=line["receipt_line_id"])
            for line in self._query(
                "SELECT * FROM supplier_invoice_lines WHERE supplier_invoice_id=? ORDER BY id",
                (row["id"],))]
        return SupplierInvoice(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], invoice_number=row["invoice_number"],
            total=Money(to_decimal(row["total"]), row["currency_code"]),
            subtotal=Money(to_decimal(row["subtotal"]), row["currency_code"]),
            tax_total=Money(to_decimal(row["tax_total"]), row["currency_code"]),
            lines=lines, captured_by_user_id=row["captured_by_user_id"],
            matched_by_user_id=row["matched_by_user_id"],
            released_by_user_id=row["released_by_user_id"],
            purchase_order_id=row["purchase_order_id"],
            direct_purchase_id=row["direct_purchase_id"], uuid_fiscal=row["uuid_fiscal"],
            status=row["status"], match_result=row["match_result"],
            created_at=row["created_at"])
