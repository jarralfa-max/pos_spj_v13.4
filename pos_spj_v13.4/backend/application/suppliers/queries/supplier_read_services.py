"""Read-only query services for suppliers. Paginated, no N+1, bank data masked.

Financial/purchase summaries read the existing finance/purchase tables and
tolerate their absence (return zeros) so the supplier context stays decoupled.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.application.suppliers.dto.supplier_dtos import (
    SupplierDashboardDTO,
    SupplierRiskDTO,
)


def _mask_clabe(clabe: str | None) -> str:
    digits = "".join(ch for ch in (clabe or "") if ch.isdigit())
    return ("•" * max(0, len(digits) - 4)) + digits[-4:] if digits else ""


class _Base:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self._conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _scalar(self, sql: str, params: tuple = (), default: Any = 0) -> Any:
        try:
            row = self._conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row and row[0] is not None else default


class SearchSuppliersQueryService(_Base):
    def search(self, *, query: str = "", status: str | None = None,
               category: str | None = None, risk_level: str | None = None,
               rating: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        conditions, params = ["1=1"], []
        if query:
            conditions.append("(m.supplier_code LIKE ? OR m.legal_name LIKE ?"
                              " OR m.trade_name LIKE ? OR m.tax_identifier LIKE ?"
                              " OR m.normalized_name LIKE ?)")
            like = f"%{query}%"
            params += [like, like, like, like, f"%{query.lower()}%"]
        if status:
            conditions.append("m.status=?"); params.append(status)
        if risk_level:
            conditions.append("m.risk_level=?"); params.append(risk_level)
        if rating:
            conditions.append("m.rating_grade=?"); params.append(rating)
        if category:
            conditions.append(
                "EXISTS (SELECT 1 FROM supplier_category_links l"
                " WHERE l.supplier_id=m.id AND l.category_code=?)")
            params.append(category)
        params += [limit, offset]
        return self._query(
            "SELECT m.id, m.supplier_code, m.legal_name, m.trade_name, m.tax_identifier,"
            " m.status, m.rating_grade, m.risk_level"
            " FROM supplier_master m"
            f" WHERE {' AND '.join(conditions)}"
            " ORDER BY m.legal_name LIMIT ? OFFSET ?", tuple(params))

    def count(self, *, query: str = "", status: str | None = None) -> int:
        conditions, params = ["1=1"], []
        if query:
            conditions.append("(supplier_code LIKE ? OR normalized_name LIKE ?)")
            params += [f"%{query}%", f"%{query.lower()}%"]
        if status:
            conditions.append("status=?"); params.append(status)
        return int(self._scalar(
            f"SELECT COUNT(*) FROM supplier_master WHERE {' AND '.join(conditions)}",
            tuple(params)))


class SupplierDetailQueryService(_Base):
    def get_header(self, supplier_id: str) -> dict | None:
        rows = self._query(
            "SELECT id, supplier_code, legal_name, trade_name, tax_identifier, status,"
            " rating_grade, risk_level, preferred_currency FROM supplier_master WHERE id=?",
            (supplier_id,))
        if not rows:
            return None
        header = rows[0]
        header["active_blocks"] = [b["block_type"] for b in self._query(
            "SELECT block_type FROM supplier_blocks WHERE supplier_id=? AND active=1",
            (supplier_id,))]
        header["counts"] = {
            "contacts": int(self._scalar("SELECT COUNT(*) FROM supplier_contacts WHERE supplier_id=?", (supplier_id,))),
            "addresses": int(self._scalar("SELECT COUNT(*) FROM supplier_addresses WHERE supplier_id=?", (supplier_id,))),
            "bank_accounts": int(self._scalar("SELECT COUNT(*) FROM supplier_bank_accounts WHERE supplier_id=?", (supplier_id,))),
            "products": int(self._scalar("SELECT COUNT(*) FROM supplier_products WHERE supplier_id=?", (supplier_id,))),
            "documents": int(self._scalar("SELECT COUNT(*) FROM supplier_documents WHERE supplier_id=?", (supplier_id,))),
        }
        return header

    def contacts(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT id, name, contact_type, role, phone_e164, email, is_primary, active"
            " FROM supplier_contacts WHERE supplier_id=? ORDER BY is_primary DESC", (supplier_id,))

    def bank_accounts(self, supplier_id: str, *, can_view_full: bool = False) -> list[dict]:
        rows = self._query(
            "SELECT id, bank_name, account_holder, currency_code, account_type, clabe,"
            " account_number, status, verified_at FROM supplier_bank_accounts"
            " WHERE supplier_id=?", (supplier_id,))
        for r in rows:
            if not can_view_full:
                r["clabe"] = _mask_clabe(r["clabe"])
                acct = r.get("account_number") or ""
                r["account_number"] = ("•" * max(0, len(acct) - 4)) + acct[-4:] if acct else ""
        return rows

    def documents(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT id, document_type, status, issued_at, expires_at, verified_at"
            " FROM supplier_documents WHERE supplier_id=? ORDER BY expires_at", (supplier_id,))

    def products(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT id, product_id, supplier_sku, purchase_unit, current_cost, currency_code,"
            " preferred FROM supplier_products WHERE supplier_id=? AND active=1", (supplier_id,))


class SupplierDashboardQueryService(_Base):
    def overview(self, *, expiring_days: int = 30) -> SupplierDashboardDTO:
        active = int(self._scalar("SELECT COUNT(*) FROM supplier_master WHERE status='ACTIVE'"))
        pending = int(self._scalar("SELECT COUNT(*) FROM supplier_master WHERE status='PENDING_APPROVAL'"))
        blocked = int(self._scalar("SELECT COUNT(*) FROM supplier_master WHERE status='BLOCKED'"))
        expiring = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_documents WHERE status IN ('EXPIRING','EXPIRED')"))
        # payables come from the finance context; tolerate their absence
        payable = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')", default=0)
        overdue = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE due_date < date('now') AND status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')",
            default=0)
        return SupplierDashboardDTO(
            active_suppliers=active, pending_approval=pending, blocked=blocked,
            payable_balance=f"{float(payable):.2f}", overdue_balance=f"{float(overdue):.2f}",
            documents_expiring=expiring)


class SupplierFinancialSummaryQueryService(_Base):
    def summary(self, supplier_id: str) -> dict:
        balance = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE supplier_id=? AND status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')",
            (supplier_id,), default=0)
        overdue = self._scalar(
            "SELECT COALESCE(SUM(CAST(outstanding_amount AS NUMERIC)),0) FROM payables"
            " WHERE supplier_id=? AND due_date < date('now')"
            " AND status NOT IN ('SETTLED','WRITTEN_OFF','CANCELLED')", (supplier_id,), default=0)
        open_docs = int(self._scalar(
            "SELECT COUNT(*) FROM payables WHERE supplier_id=? AND status NOT IN"
            " ('SETTLED','WRITTEN_OFF','CANCELLED')", (supplier_id,), default=0))
        return {"balance": f"{float(balance):.2f}", "overdue": f"{float(overdue):.2f}",
                "open_documents": open_docs}


class SupplierPerformanceQueryService(_Base):
    def performance(self, supplier_id: str) -> dict:
        row = self._query(
            "SELECT score, rating_grade, period FROM supplier_evaluations"
            " WHERE supplier_id=? ORDER BY period DESC LIMIT 1", (supplier_id,))
        latest = row[0] if row else {"score": None, "rating_grade": None, "period": None}
        avg = self._scalar(
            "SELECT AVG(score) FROM supplier_evaluations WHERE supplier_id=?",
            (supplier_id,), default=None)
        return {"latest_score": latest["score"], "latest_rating": latest["rating_grade"],
                "latest_period": latest["period"],
                "average_score": round(float(avg), 1) if avg is not None else None}


class SupplierPurchaseHistoryQueryService(_Base):
    def history(self, supplier_id: str, *, limit: int = 50) -> list[dict]:
        try:
            return self._query(
                "SELECT c.id, c.fecha, c.total FROM compras c WHERE c.proveedor_id=?"
                " ORDER BY c.fecha DESC LIMIT ?", (supplier_id, limit))
        except sqlite3.OperationalError:
            return []


class SupplierRiskQueryService(_Base):
    """Computes supplier risk with explicit causes (never just a color)."""

    def assess(self, supplier_id: str) -> SupplierRiskDTO:
        causes: list[str] = []
        weight = 0

        expired = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_documents WHERE supplier_id=? AND status='EXPIRED'",
            (supplier_id,)))
        if expired:
            causes.append(f"{expired} documento(s) vencido(s)"); weight += 2 * expired

        unverified = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_bank_accounts WHERE supplier_id=?"
            " AND status!='VERIFIED'", (supplier_id,)))
        if unverified:
            causes.append("Cuenta bancaria sin verificar"); weight += 2

        active_blocks = int(self._scalar(
            "SELECT COUNT(*) FROM supplier_blocks WHERE supplier_id=? AND active=1",
            (supplier_id,)))
        if active_blocks:
            causes.append(f"{active_blocks} bloqueo(s) activo(s)"); weight += 2 * active_blocks

        rating = self._scalar(
            "SELECT rating_grade FROM supplier_master WHERE id=?", (supplier_id,), default=None)
        if rating in ("C", "D"):
            causes.append(f"Evaluación baja (rating {rating})")
            weight += 1 if rating == "C" else 3

        if weight >= 6:
            level = "CRITICAL"
        elif weight >= 4:
            level = "HIGH"
        elif weight >= 2:
            level = "MEDIUM"
        else:
            level = "LOW"
        return SupplierRiskDTO(supplier_id=supplier_id, level=level, causes=tuple(causes))
