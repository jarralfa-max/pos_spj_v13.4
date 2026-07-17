"""Read-only query services for the enterprise procurement UI (requisitions,
orders, receipts, invoices). Paginated, no business logic; the UI never issues
SQL — it asks these services for display-ready rows."""

from __future__ import annotations

import sqlite3
from typing import Any


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
    def count(self, *, status: str | None = None, search: str = "") -> int:
        where, params = _where(("status",), status, search, ("document_number", "branch_id"))
        return int(self._scalar(
            f"SELECT COUNT(*) FROM purchase_requisitions{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0) -> list[dict]:
        where, params = _where(("status",), status, search, ("document_number", "branch_id"))
        return self._query(
            "SELECT id, document_number, branch_id, requested_by_user_id, purchase_type,"
            " priority, status, created_at FROM purchase_requisitions"
            f"{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*params, limit, offset))

    def detail(self, requisition_id: str) -> dict | None:
        row = self._query_one("SELECT * FROM purchase_requisitions WHERE id=?",
                              (requisition_id,))
        if row is None:
            return None
        row["lines"] = self._query(
            "SELECT product_id, quantity, estimated_unit_cost FROM"
            " purchase_requisition_lines WHERE requisition_id=? ORDER BY id",
            (requisition_id,))
        return row


class OrderReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "") -> int:
        where, params = _where(("status",), status, search, ("document_number", "supplier_id"))
        return int(self._scalar(f"SELECT COUNT(*) FROM purchase_orders{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0) -> list[dict]:
        where, params = _where(("status",), status, search, ("document_number", "supplier_id"))
        return self._query(
            "SELECT id, document_number, supplier_id, branch_id, status, total, version,"
            " currency_code, created_at FROM purchase_orders"
            f"{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*params, limit, offset))

    def detail(self, order_id: str) -> dict | None:
        row = self._query_one("SELECT * FROM purchase_orders WHERE id=?", (order_id,))
        if row is None:
            return None
        row["lines"] = self._query(
            "SELECT product_id, description, ordered_quantity, unit_price, received_quantity,"
            " accepted_quantity FROM purchase_order_lines WHERE purchase_order_id=? ORDER BY id",
            (order_id,))
        row["versions"] = self._query(
            "SELECT version, reason, changed_by_user_id, created_at FROM"
            " purchase_order_versions WHERE purchase_order_id=? ORDER BY version",
            (order_id,))
        return row


class InvoiceReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "") -> int:
        where, params = _where(("status",), status, search,
                               ("document_number", "supplier_id", "invoice_number"))
        return int(self._scalar(f"SELECT COUNT(*) FROM supplier_invoices{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0) -> list[dict]:
        where, params = _where(("status",), status, search,
                               ("document_number", "supplier_id", "invoice_number"))
        return self._query(
            "SELECT id, document_number, supplier_id, invoice_number, total, currency_code,"
            " status, match_result, purchase_order_id, created_at FROM supplier_invoices"
            f"{where} ORDER BY created_at DESC LIMIT ? OFFSET ?", (*params, limit, offset))

    def detail(self, invoice_id: str) -> dict | None:
        row = self._query_one("SELECT * FROM supplier_invoices WHERE id=?", (invoice_id,))
        if row is None:
            return None
        row["matches"] = self._query(
            "SELECT result, released_by_user_id, notes, created_at FROM"
            " supplier_invoice_matches WHERE supplier_invoice_id=? ORDER BY created_at",
            (invoice_id,))
        return row


def _where(status_cols: tuple[str, ...], status, search: str,
           search_cols: tuple[str, ...]) -> tuple[str, list]:
    clauses, params = [], []
    if status:
        clauses.append(f"{status_cols[0]} = ?")
        params.append(status)
    if search and search.strip():
        like = f"%{search.strip()}%"
        ors = " OR ".join(f"{c} LIKE ?" for c in search_cols)
        clauses.append(f"({ors})")
        params.extend([like] * len(search_cols))
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params
