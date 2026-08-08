"""Read-only query services for the Cotizaciones/Adjudicación UI. Paginated,
no business logic; pure SQL projections — the UI never issues SQL and the
comparison ranking here is display-only (the domain's own
``QuoteComparison``/``AwardSupplierQuoteUseCase`` remain the source of truth
for what actually gets awarded)."""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.procurement.dto.quotation_dtos import (
    ComparisonRowDTO,
    RfqDetailDTO,
    RfqInvitationDTO,
    RfqQuoteSummaryDTO,
    RfqRowDTO,
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


class RfqReadService(_Base):
    def count(self, *, status: str | None = None, search: str = "") -> int:
        where, params = self._where(status, search)
        return int(self._scalar(
            f"SELECT COUNT(*) FROM requests_for_quotation{where}", tuple(params)))

    def list(self, *, status: str | None = None, search: str = "", limit: int = 50,
             offset: int = 0) -> list[RfqRowDTO]:
        where, params = self._where(status, search)
        rows = self._query(
            "SELECT r.id, r.document_number, r.status, r.requisition_id, r.created_at,"
            " (SELECT COUNT(*) FROM rfq_supplier_invitations i WHERE i.rfq_id=r.id)"
            " invited_count,"
            " (SELECT COUNT(DISTINCT supplier_id) FROM supplier_quotes q"
            "  WHERE q.rfq_id=r.id) quoted_count,"
            " EXISTS(SELECT 1 FROM purchase_awards a WHERE a.rfq_id=r.id) awarded"
            f" FROM requests_for_quotation r{where}"
            " ORDER BY r.created_at DESC LIMIT ? OFFSET ?", (*params, limit, offset))
        return [RfqRowDTO(
            id=r["id"], document_number=r["document_number"], status=r["status"],
            requisition_id=r["requisition_id"], invited_count=r["invited_count"],
            quoted_count=r["quoted_count"], awarded=bool(r["awarded"]),
            created_at=r["created_at"]) for r in rows]

    def _supplier_name(self, supplier_id: str) -> str:
        row = self._query_one("SELECT nombre FROM proveedores WHERE id=?", (supplier_id,))
        return str(row["nombre"]) if row else "Proveedor no disponible"

    def detail(self, rfq_id: str) -> RfqDetailDTO | None:
        row = self._query_one(
            "SELECT id, document_number, status, requisition_id, response_deadline,"
            " created_at FROM requests_for_quotation WHERE id=?", (rfq_id,))
        if row is None:
            return None
        quoted_suppliers = {
            r["supplier_id"] for r in self._query(
                "SELECT DISTINCT supplier_id FROM supplier_quotes WHERE rfq_id=?", (rfq_id,))}
        invitation_rows = self._query(
            "SELECT supplier_id, status FROM rfq_supplier_invitations"
            " WHERE rfq_id=? ORDER BY invited_at", (rfq_id,))
        invitations = [RfqInvitationDTO(
            supplier_id=ir["supplier_id"], supplier_name=self._supplier_name(ir["supplier_id"]),
            status=ir["status"], has_quote=ir["supplier_id"] in quoted_suppliers)
            for ir in invitation_rows]
        quote_rows = self._query(
            "SELECT q.id, q.supplier_id, q.currency_code, q.lead_time_days,"
            " COALESCE(SUM(CAST(l.quantity AS NUMERIC) * CAST(l.unit_price AS NUMERIC)"
            " - CAST(l.discount AS NUMERIC) + CAST(l.tax AS NUMERIC)), 0) total,"
            " COUNT(l.id) line_count"
            " FROM supplier_quotes q LEFT JOIN supplier_quote_lines l ON l.quote_id=q.id"
            " WHERE q.rfq_id=? GROUP BY q.id ORDER BY q.created_at", (rfq_id,))
        quotes = [RfqQuoteSummaryDTO(
            quote_id=qr["id"], supplier_id=qr["supplier_id"],
            supplier_name=self._supplier_name(qr["supplier_id"]),
            total=str(qr["total"]), currency_code=qr["currency_code"],
            lead_time_days=qr["lead_time_days"], line_count=qr["line_count"])
            for qr in quote_rows]
        awarded = bool(self._scalar(
            "SELECT COUNT(*) FROM purchase_awards WHERE rfq_id=?", (rfq_id,)))
        return RfqDetailDTO(
            id=row["id"], document_number=row["document_number"], status=row["status"],
            created_at=row["created_at"], requisition_id=row["requisition_id"],
            response_deadline=row["response_deadline"], awarded=awarded,
            invitations=invitations, quotes=quotes)

    def comparison(self, rfq_id: str) -> list[ComparisonRowDTO]:
        """Every quoted (product, supplier) line for this RFQ, ranked cheapest
        first within each product group — display-only ranking."""
        rows = self._query(
            "SELECT l.id quote_line_id, l.product_id, l.quantity, l.unit_price,"
            " l.currency_code, q.id quote_id, q.supplier_id, q.lead_time_days,"
            " COALESCE(p.nombre, '—') AS supplier_name"
            " FROM supplier_quote_lines l JOIN supplier_quotes q ON q.id=l.quote_id"
            " LEFT JOIN proveedores p ON p.id=q.supplier_id"
            " WHERE q.rfq_id=?"
            " ORDER BY l.product_id, CAST(l.unit_price AS NUMERIC), q.lead_time_days",
            (rfq_id,))
        result: list[ComparisonRowDTO] = []
        best_seen: set[str] = set()
        for r in rows:
            is_best = r["product_id"] not in best_seen
            best_seen.add(r["product_id"])
            result.append(ComparisonRowDTO(
                product_id=r["product_id"], quote_id=r["quote_id"],
                quote_line_id=r["quote_line_id"], supplier_id=r["supplier_id"],
                supplier_name=r["supplier_name"], quantity=r["quantity"],
                unit_price=r["unit_price"], lead_time_days=r["lead_time_days"],
                currency_code=r["currency_code"], is_best=is_best))
        return result

    def _where(self, status: str | None, search: str) -> tuple[str, list]:
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search.strip():
            clauses.append("document_number LIKE ?")
            params.append(f"%{search.strip()}%")
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params
