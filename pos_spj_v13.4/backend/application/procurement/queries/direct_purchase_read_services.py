"""Read-only query services for the direct-purchase UI (paginated, no business
logic). The UI never issues SQL; it asks these services for display-ready rows."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.procurement.dto.direct_purchase_dtos import (
    DirectPurchaseDetailDTO,
    DirectPurchaseLineDTO,
    DirectPurchaseRowDTO,
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


class DirectPurchaseReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "") -> int:
        where, params = self._where(status, search)
        return int(self._scalar(
            f"SELECT COUNT(*) FROM direct_purchases{where}", tuple(params), default=0))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0) -> list[DirectPurchaseRowDTO]:
        where, params = self._where(status, search)
        rows = self._query(
            "SELECT id, document_number, supplier_id, branch_id, status, total,"
            " currency_code, payment_condition, created_at"
            f" FROM direct_purchases{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [DirectPurchaseRowDTO(
            id=r["id"], document_number=r["document_number"], supplier_id=r["supplier_id"],
            branch_id=r["branch_id"], status=r["status"], total=r["total"],
            currency_code=r["currency_code"], payment_condition=r["payment_condition"],
            created_at=r["created_at"]) for r in rows]

    def get_detail(self, direct_purchase_id: str) -> DirectPurchaseDetailDTO | None:
        row = self._query_one("SELECT * FROM direct_purchases WHERE id=?",
                              (direct_purchase_id,))
        if row is None:
            return None
        line_rows = self._query(
            "SELECT product_id, description, quantity, unit_cost, discount, tax, line_total,"
            " purchase_unit, inventory_unit, conversion_factor"
            " FROM direct_purchase_lines WHERE direct_purchase_id=? ORDER BY id",
            (direct_purchase_id,))
        lines = [DirectPurchaseLineDTO(
            product_id=lr["product_id"], description=lr["description"] or "",
            quantity=lr["quantity"], unit_cost=lr["unit_cost"], discount=lr["discount"],
            tax=lr["tax"], line_total=lr["line_total"], purchase_unit=lr["purchase_unit"],
            inventory_unit=lr["inventory_unit"], conversion_factor=lr["conversion_factor"])
            for lr in line_rows]
        return DirectPurchaseDetailDTO(
            id=row["id"], document_number=row["document_number"],
            supplier_id=row["supplier_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], status=row["status"], mode=row["mode"],
            payment_condition=row["payment_condition"], currency_code=row["currency_code"],
            subtotal=row["subtotal"], tax_total=row["tax_total"], total=row["total"],
            authorization_reason=row["authorization_reason"] or "",
            authorized_by_user_id=row["authorized_by_user_id"],
            created_by_user_id=row["created_by_user_id"], lines=lines)

    def _where(self, status: str | None, search: str) -> tuple[str, list]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search.strip():
            clauses.append("(document_number LIKE ? OR supplier_id LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params


class SupplierPickerQueryService(_Base):
    """Feeds the supplier search box from the canonical supplier master, falling
    back to the legacy table when the master is not present yet."""

    def search(self, query: str, *, limit: int = 25) -> list[dict]:
        like = f"%{query.strip()}%"
        rows = self._query(
            "SELECT id, legal_name AS name, supplier_code AS code, status"
            " FROM supplier_master"
            " WHERE legal_name LIKE ? OR trade_name LIKE ? OR supplier_code LIKE ?"
            " ORDER BY legal_name LIMIT ?", (like, like, like, limit))
        if rows:
            return rows
        # legacy fallback (opaque id/name only)
        return self._query(
            "SELECT id, nombre AS name, '' AS code, '' AS status FROM proveedores"
            " WHERE nombre LIKE ? ORDER BY nombre LIMIT ?", (like, limit))
