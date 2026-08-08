"""Read-only query services for the enterprise procurement UI (requisitions,
orders, receipts, invoices). Paginated, no business logic; the UI never issues
SQL — it asks these services for display-ready rows."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.procurement.dto.enterprise_dtos import (
    GoodsReceiptLineDTO,
    InvoiceDetailDTO,
    InvoiceLineDTO,
    InvoiceMatchDTO,
    InvoiceRowDTO,
    OrderDetailDTO,
    OrderLineDTO,
    OrderRowDTO,
    OrderVersionDTO,
    ReceiptDetailDTO,
    ReceiptDiscrepancyDTO,
    ReceiptRowDTO,
    RequisitionDetailDTO,
    RequisitionLineDTO,
    RequisitionRowDTO,
)


class _Base:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cur = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        try:
            row = self._conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row and row[0] is not None else default


class RequisitionReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "", branch_id=None,
              start_date=None, end_date=None) -> int:
        where, params = _where(("status",), status, search, ("document_number", "branch_id"),
                               branch_id, start_date, end_date)
        return int(self._scalar(
            f"SELECT COUNT(*) FROM purchase_requisitions{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0, branch_id=None, start_date=None,
             end_date=None) -> list[RequisitionRowDTO]:
        where, params = _where(("status",), status, search, ("document_number", "branch_id"),
                               branch_id, start_date, end_date)
        rows = self._query(
            "SELECT purchase_requisitions.id, document_number, branch_id,"
            " requested_by_user_id, purchase_type, priority, status,"
            " purchase_requisitions.created_at, COALESCE(s.nombre, '—') AS branch_name"
            " FROM purchase_requisitions"
            " LEFT JOIN sucursales s ON s.id = purchase_requisitions.branch_id"
            f"{where} ORDER BY purchase_requisitions.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [RequisitionRowDTO(
            id=r["id"], document_number=r["document_number"], branch_id=r["branch_id"],
            branch_name=r["branch_name"], requested_by_user_id=r["requested_by_user_id"],
            purchase_type=r["purchase_type"], priority=r["priority"], status=r["status"],
            created_at=r["created_at"]) for r in rows]

    def _requester_name(self, user_id: str | None) -> str:
        if not user_id:
            return "—"
        user = self._query_one("SELECT nombre FROM usuarios WHERE id=?", (user_id,))
        return str(user["nombre"]) if user else "Usuario no disponible"

    def detail(self, requisition_id: str) -> RequisitionDetailDTO | None:
        row = self._query_one("SELECT * FROM purchase_requisitions WHERE id=?",
                              (requisition_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT id, product_id, quantity, estimated_unit_cost, purchase_nature FROM"
            " purchase_requisition_lines WHERE requisition_id=? ORDER BY id",
            (requisition_id,))
        lines = [RequisitionLineDTO(
            id=lr["id"], product_id=lr["product_id"], quantity=lr["quantity"],
            estimated_unit_cost=lr["estimated_unit_cost"],
            purchase_nature=lr["purchase_nature"]) for lr in line_rows]
        related_documents = (
            self._query(
                "SELECT id,document_number,'RFQ' AS document_type,status,created_at"
                " FROM requests_for_quotation WHERE requisition_id=?", (requisition_id,))
            + self._query(
                "SELECT id,document_number,'PO' AS document_type,status,created_at"
                " FROM purchase_orders WHERE source_requisition_id=?", (requisition_id,))
            + self._query(
                "SELECT id,document_number,'DIRECT_PURCHASE' AS document_type,status,created_at"
                " FROM direct_purchases WHERE source_requisition_id=?", (requisition_id,))
        )
        timeline = self._query(
            "SELECT action,actor_user_id,reason,created_at FROM procurement_audit_log"
            " WHERE document_id=? ORDER BY created_at", (requisition_id,))
        return RequisitionDetailDTO(
            id=row["id"], document_number=row["document_number"], branch_id=row["branch_id"],
            requested_by_user_id=row["requested_by_user_id"],
            requested_by_name=self._requester_name(row["requested_by_user_id"]),
            purchase_type=row["purchase_type"], priority=row["priority"],
            business_reason=row["business_reason"] or "", status=row["status"],
            source_channel=row["source_channel"], created_at=row["created_at"],
            updated_at=row["updated_at"], required_date=row["required_date"],
            source_reference_id=row["source_reference_id"],
            approved_by_user_id=row["approved_by_user_id"], operation_id=row["operation_id"],
            lines=lines, related_documents=related_documents, timeline=timeline)


class OrderReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "", branch_id=None,
              start_date=None, end_date=None) -> int:
        where, params = _where(("status",), status, search, ("document_number", "supplier_id"),
                               branch_id, start_date, end_date)
        return int(self._scalar(f"SELECT COUNT(*) FROM purchase_orders{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0, branch_id=None, start_date=None,
             end_date=None) -> list[OrderRowDTO]:
        where, params = _where(("status",), status, search, ("document_number", "supplier_id"),
                               branch_id, start_date, end_date)
        rows = self._query(
            "SELECT purchase_orders.id, document_number, supplier_id, branch_id, status, total,"
            " version, currency_code, purchase_orders.created_at,"
            " COALESCE(p.nombre, '—') AS supplier_name FROM purchase_orders"
            " LEFT JOIN proveedores p ON p.id = purchase_orders.supplier_id"
            f"{where} ORDER BY purchase_orders.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [OrderRowDTO(
            id=r["id"], document_number=r["document_number"], supplier_id=r["supplier_id"],
            supplier_name=r["supplier_name"], branch_id=r["branch_id"], status=r["status"],
            total=r["total"], version=r["version"], currency_code=r["currency_code"],
            created_at=r["created_at"]) for r in rows]

    def _supplier_name(self, supplier_id: str | None) -> str:
        if not supplier_id:
            return "—"
        supplier = self._query_one("SELECT nombre FROM proveedores WHERE id=?", (supplier_id,))
        return str(supplier["nombre"]) if supplier else "Proveedor no disponible"

    def detail(self, order_id: str) -> OrderDetailDTO | None:
        row = self._query_one("SELECT * FROM purchase_orders WHERE id=?", (order_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT product_id, description, ordered_quantity, unit_price, received_quantity,"
            " accepted_quantity FROM purchase_order_lines WHERE purchase_order_id=? ORDER BY id",
            (order_id,))
        lines = [OrderLineDTO(
            product_id=lr["product_id"], description=lr["description"] or "",
            ordered_quantity=lr["ordered_quantity"], unit_price=lr["unit_price"],
            received_quantity=lr["received_quantity"],
            accepted_quantity=lr["accepted_quantity"]) for lr in line_rows]
        version_rows = self._query(
            "SELECT version, reason, changed_by_user_id, created_at FROM"
            " purchase_order_versions WHERE purchase_order_id=? ORDER BY version",
            (order_id,))
        versions = [OrderVersionDTO(
            version=vr["version"], reason=vr["reason"] or "",
            changed_by_user_id=vr["changed_by_user_id"], created_at=vr["created_at"])
            for vr in version_rows]
        related_documents = self._query(
            "SELECT id,document_number,'INVOICE' AS document_type,status,created_at"
            " FROM supplier_invoices WHERE purchase_order_id=?", (order_id,))
        timeline = self._query(
            "SELECT action,actor_user_id,reason,created_at FROM procurement_audit_log"
            " WHERE document_id=? ORDER BY created_at", (order_id,))
        return OrderDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], supplier_name=self._supplier_name(row["supplier_id"]),
            branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
            currency_code=row["currency_code"], purchase_type=row["purchase_type"],
            status=row["status"], total=row["total"], version=row["version"],
            created_at=row["created_at"], updated_at=row["updated_at"],
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            source_requisition_id=row["source_requisition_id"],
            source_rfq_id=row["source_rfq_id"], source_award_id=row["source_award_id"],
            operation_id=row["operation_id"], lines=lines, versions=versions,
            related_documents=related_documents, timeline=timeline)


class InvoiceReadService(_Base):
    def billable_documents(self, *, branch_id: str, search="", limit=50) -> list[dict]:
        like = f"%{search.strip()}%"
        return self._query(
            "SELECT o.id,o.document_number,o.supplier_id,p.nombre,'PURCHASE_ORDER' document_type"
            " FROM purchase_orders o JOIN proveedores p ON p.id=o.supplier_id"
            " WHERE o.branch_id=? AND o.status IN ('PARTIALLY_RECEIVED','RECEIVED')"
            " AND (o.document_number LIKE ? OR p.nombre LIKE ?) UNION ALL"
            " SELECT d.id,d.document_number,d.supplier_id,p.nombre,'DIRECT_PURCHASE'"
            " FROM direct_purchases d JOIN proveedores p ON p.id=d.supplier_id"
            " WHERE d.branch_id=? AND d.status IN ('PARTIALLY_RECEIVED','RECEIVED')"
            " AND (d.document_number LIKE ? OR p.nombre LIKE ?) LIMIT ?",
            (branch_id, like, like, branch_id, like, like, limit))

    def billable_lines(self, document_type: str, document_id: str) -> list[dict]:
        if document_type == "PURCHASE_ORDER":
            return self._query(
                "SELECT l.id source_line_id,l.product_id,l.description,"
                " l.ordered_quantity quantity,l.unit_price, '0' tax,"
                " COALESCE((SELECT SUM(CAST(r.accepted_quantity AS NUMERIC))"
                " FROM goods_receipt_lines r JOIN goods_receipts g ON g.id=r.goods_receipt_id"
                " WHERE g.purchase_order_id=? AND g.status='COMPLETED'"
                " AND r.product_id=l.product_id),0) accepted_quantity"
                " FROM purchase_order_lines l WHERE l.purchase_order_id=?",
                (document_id, document_id))
        return self._query(
            "SELECT l.id source_line_id,l.product_id,l.description,l.quantity,l.unit_cost unit_price,"
            " l.tax,COALESCE((SELECT SUM(CAST(r.accepted_quantity AS NUMERIC))"
            " FROM goods_receipt_lines r JOIN goods_receipts g ON g.id=r.goods_receipt_id"
            " WHERE g.direct_purchase_id=? AND g.status='COMPLETED'"
            " AND r.product_id=l.product_id),0) accepted_quantity"
            " FROM direct_purchase_lines l WHERE l.direct_purchase_id=?",
            (document_id, document_id))

    def resolve_billable_document(self, document_id: str) -> dict | None:
        """Identify a billable document's type + supplier without the caller
        having to already know whether it's a PO or a direct purchase."""
        row = self._query_one(
            "SELECT o.supplier_id, COALESCE(p.nombre,'—') AS supplier_name,"
            " 'PURCHASE_ORDER' AS document_type FROM purchase_orders o"
            " LEFT JOIN proveedores p ON p.id=o.supplier_id WHERE o.id=?", (document_id,))
        if row is not None:
            return row
        return self._query_one(
            "SELECT d.supplier_id, COALESCE(p.nombre,'—') AS supplier_name,"
            " 'DIRECT_PURCHASE' AS document_type FROM direct_purchases d"
            " LEFT JOIN proveedores p ON p.id=d.supplier_id WHERE d.id=?", (document_id,))

    def count(self, *, status: str | None = None, search: str = "", branch_id=None,
              start_date=None, end_date=None) -> int:
        where, params = _where(("status",), status, search,
                               ("document_number", "supplier_id", "invoice_number"),
                               branch_id, start_date, end_date,
                               "(purchase_order_id IN (SELECT id FROM purchase_orders WHERE branch_id=?)"
                               " OR direct_purchase_id IN (SELECT id FROM direct_purchases WHERE branch_id=?))")
        return int(self._scalar(f"SELECT COUNT(*) FROM supplier_invoices{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0, branch_id=None, start_date=None,
             end_date=None) -> list[InvoiceRowDTO]:
        where, params = _where(("status",), status, search,
                               ("document_number", "supplier_id", "invoice_number"),
                               branch_id, start_date, end_date,
                               "(purchase_order_id IN (SELECT id FROM purchase_orders WHERE branch_id=?)"
                               " OR direct_purchase_id IN (SELECT id FROM direct_purchases WHERE branch_id=?))")
        rows = self._query(
            "SELECT supplier_invoices.id, document_number, supplier_id, invoice_number, total,"
            " currency_code, status, match_result, purchase_order_id,"
            " supplier_invoices.created_at, COALESCE(p.nombre, '—') AS supplier_name"
            " FROM supplier_invoices"
            " LEFT JOIN proveedores p ON p.id = supplier_invoices.supplier_id"
            f"{where} ORDER BY supplier_invoices.created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [InvoiceRowDTO(
            id=r["id"], document_number=r["document_number"], supplier_id=r["supplier_id"],
            supplier_name=r["supplier_name"], invoice_number=r["invoice_number"],
            total=r["total"], currency_code=r["currency_code"], status=r["status"],
            match_result=r["match_result"], purchase_order_id=r["purchase_order_id"],
            created_at=r["created_at"]) for r in rows]

    def _supplier_name(self, supplier_id: str | None) -> str:
        if not supplier_id:
            return "—"
        supplier = self._query_one("SELECT nombre FROM proveedores WHERE id=?", (supplier_id,))
        return str(supplier["nombre"]) if supplier else "Proveedor no disponible"

    def detail(self, invoice_id: str) -> InvoiceDetailDTO | None:
        row = self._query_one("SELECT * FROM supplier_invoices WHERE id=?", (invoice_id,))
        if row is None:
            return None
        match_rows = self._query(
            "SELECT result, released_by_user_id, notes, created_at FROM"
            " supplier_invoice_matches WHERE supplier_invoice_id=? ORDER BY created_at",
            (invoice_id,))
        matches = [InvoiceMatchDTO(
            result=mr["result"], released_by_user_id=mr["released_by_user_id"],
            notes=mr["notes"] or "", created_at=mr["created_at"]) for mr in match_rows]
        line_rows = self._query(
            "SELECT id,product_id,invoiced_quantity,unit_price,tax,"
            " purchase_order_line_id,direct_purchase_line_id,receipt_line_id"
            " FROM supplier_invoice_lines WHERE supplier_invoice_id=? ORDER BY id",
            (invoice_id,))
        lines = [InvoiceLineDTO(
            id=lr["id"], product_id=lr["product_id"], invoiced_quantity=lr["invoiced_quantity"],
            unit_price=lr["unit_price"], tax=lr["tax"],
            purchase_order_line_id=lr["purchase_order_line_id"],
            direct_purchase_line_id=lr["direct_purchase_line_id"],
            receipt_line_id=lr["receipt_line_id"]) for lr in line_rows]
        document_type = "PURCHASE_ORDER" if row.get("purchase_order_id") else "DIRECT_PURCHASE"
        document_id = row.get("purchase_order_id") or row.get("direct_purchase_id")
        comparison = self.billable_lines(document_type, document_id) if document_id else []
        return InvoiceDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], supplier_name=self._supplier_name(row["supplier_id"]),
            invoice_number=row["invoice_number"], subtotal=row["subtotal"],
            tax_total=row["tax_total"], total=row["total"], currency_code=row["currency_code"],
            status=row["status"], captured_by_user_id=row["captured_by_user_id"],
            created_at=row["created_at"], purchase_order_id=row["purchase_order_id"],
            direct_purchase_id=row["direct_purchase_id"], match_result=row["match_result"],
            matched_by_user_id=row["matched_by_user_id"],
            released_by_user_id=row["released_by_user_id"], operation_id=row["operation_id"],
            lines=lines, matches=matches, comparison=comparison)


class ReceiptReadService(_Base):
    def list(self, *, branch_id: str, warehouse_id: str, limit=100) -> list[ReceiptRowDTO]:
        rows = self._query(
            "SELECT g.id,g.document_number,g.supplier_id,g.status,g.created_at,"
            " COALESCE(SUM(CAST(l.received_quantity AS NUMERIC)),0) received,"
            " COALESCE(SUM(CAST(l.accepted_quantity AS NUMERIC)),0) accepted,"
            " COALESCE(SUM(CAST(l.rejected_quantity AS NUMERIC)),0) rejected,"
            " (SELECT COUNT(*) FROM receipt_discrepancies d WHERE d.goods_receipt_id=g.id) differences"
            " FROM goods_receipts g"
            " LEFT JOIN goods_receipt_lines l ON l.goods_receipt_id=g.id"
            " WHERE g.branch_id=? AND g.warehouse_id=? GROUP BY g.id"
            " ORDER BY g.created_at DESC LIMIT ?", (branch_id, warehouse_id, limit))
        result = []
        for row in rows:
            supplier = self._query_one("SELECT nombre FROM proveedores WHERE id=?",
                                       (row["supplier_id"],))
            supplier_name = supplier["nombre"] if supplier else "Proveedor no disponible"
            result.append(ReceiptRowDTO(
                id=row["id"], document_number=row["document_number"],
                supplier_id=row["supplier_id"], supplier_name=supplier_name,
                status=row["status"], created_at=row["created_at"], received=row["received"],
                accepted=row["accepted"], rejected=row["rejected"],
                differences=row["differences"]))
        return result

    def detail(self, receipt_id: str) -> ReceiptDetailDTO | None:
        row = self._query_one("SELECT * FROM goods_receipts WHERE id=?", (receipt_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT id,product_id,ordered_quantity,received_quantity,accepted_quantity,"
            " rejected_quantity,lot,expiration,temperature FROM goods_receipt_lines"
            " WHERE goods_receipt_id=? ORDER BY id", (receipt_id,))
        lines = [GoodsReceiptLineDTO(
            id=lr["id"], product_id=lr["product_id"], ordered_quantity=lr["ordered_quantity"],
            received_quantity=lr["received_quantity"], accepted_quantity=lr["accepted_quantity"],
            rejected_quantity=lr["rejected_quantity"], lot=lr["lot"],
            expiration=lr["expiration"], temperature=lr["temperature"]) for lr in line_rows]
        difference_rows = self._query(
            "SELECT discrepancy_type,expected,actual,reason FROM receipt_discrepancies"
            " WHERE goods_receipt_id=? ORDER BY id", (receipt_id,))
        differences = [ReceiptDiscrepancyDTO(
            discrepancy_type=dr["discrepancy_type"], expected=dr["expected"],
            actual=dr["actual"], reason=dr["reason"] or "") for dr in difference_rows]
        invoices = self._query(
            "SELECT id,document_number,invoice_number,status,match_result,total"
            " FROM supplier_invoices WHERE purchase_order_id=? OR direct_purchase_id=?",
            (row.get("purchase_order_id"), row.get("direct_purchase_id")))
        return ReceiptDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], status=row["status"],
            created_at=row["created_at"], purchase_order_id=row["purchase_order_id"],
            direct_purchase_id=row["direct_purchase_id"],
            received_by_user_id=row["received_by_user_id"], operation_id=row["operation_id"],
            lines=lines, differences=differences, invoices=invoices)


def _where(status_cols: tuple[str, ...], status, search: str,
           search_cols: tuple[str, ...], branch_id=None, start_date=None,
           end_date=None, branch_clause="branch_id = ?") -> tuple[str, list]:
    clauses, params = [], []
    if status:
        clauses.append(f"{status_cols[0]} = ?")
        params.append(status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        ors = " OR ".join(f"{c} LIKE ?" for c in search_cols)
        clauses.append(f"({ors})")
        params.extend([like] * len(search_cols))
    if branch_id:
        clauses.append(branch_clause)
        params.extend([branch_id] * branch_clause.count("?"))
    if start_date:
        clauses.append("substr(created_at,1,10) >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("substr(created_at,1,10) <= ?")
        params.append(end_date)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
