"""PricingReadService — read side for the enterprise pricing/costing UI (PRC-7).

Returns display rows and overview counts for the module. Read-only, parametrized
SQL over the canonical pricing schema (``price_list`` / ``product_price`` /
``volume_price`` / ``product_cost`` / ``price_change_log``). The presenter/UI never
issue SQL — they consume these results.

Product name/code come from the canonical ``products`` master via LEFT JOIN when
present (never from the legacy ``productos`` — see the pricing boundary guardrail).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def _dec(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class PricingReadService:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── overview ────────────────────────────────────────────────────────────
    def overview_counts(self) -> dict:
        c = self._conn
        lists_active = c.execute(
            "SELECT COUNT(*) FROM price_list WHERE status='ACTIVE'").fetchone()[0]
        lists_pending = c.execute(
            "SELECT COUNT(*) FROM price_list WHERE status IN ('DRAFT','UNDER_REVIEW')"
        ).fetchone()[0]
        priced = c.execute(
            "SELECT COUNT(DISTINCT product_id) FROM product_price").fetchone()[0]
        costed = c.execute(
            "SELECT COUNT(DISTINCT product_id) FROM product_cost").fetchone()[0]
        volume_tiers = c.execute("SELECT COUNT(*) FROM volume_price").fetchone()[0]
        # Decimal-only: comparación en Python (nunca CAST AS REAL)
        below_min = 0
        for r in c.execute("SELECT sale_price, min_price FROM product_price "
                           "WHERE min_price IS NOT NULL").fetchall():
            sale, mn = _dec(r["sale_price"]), _dec(r["min_price"])
            if sale is not None and mn is not None and sale < mn:
                below_min += 1
        return {"lists_active": lists_active, "lists_pending": lists_pending,
                "priced": priced, "costed": costed, "volume_tiers": volume_tiers,
                "below_min": below_min}

    # ── price lists ─────────────────────────────────────────────────────────
    def list_price_lists(self, *, kind: str | None = None, limit: int = 200) -> list[dict]:
        sql = ("SELECT id, code, name, kind, status, discount_pct FROM price_list "
               "WHERE 1=1")
        params: list = []
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY kind, name LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "code": r["code"], "name": r["name"], "kind": r["kind"],
                 "status": r["status"], "discount_pct": r["discount_pct"]} for r in rows]

    # ── product prices ──────────────────────────────────────────────────────
    def list_product_prices(self, *, query: str | None = None, list_id: str | None = None,
                            limit: int = 200) -> list[dict]:
        has_products = self._table_exists("products")
        name_sel = "p.code AS product_code, p.name AS product_name" if has_products \
            else "NULL AS product_code, NULL AS product_name"
        join = "LEFT JOIN products p ON p.id = pp.product_id" if has_products else ""
        sql = (f"SELECT pp.id, pp.product_id, {name_sel}, pp.branch_id, pp.sale_price, "
               f"pp.sale_price_currency, pp.min_price, pl.code AS list_code, pl.name AS list_name "
               f"FROM product_price pp "
               f"JOIN price_list pl ON pl.id = pp.price_list_id {join} WHERE 1=1")
        params: list = []
        if list_id:
            sql += " AND pp.price_list_id=?"
            params.append(list_id)
        if query and has_products:
            sql += " AND (p.name_normalized LIKE ? OR p.code LIKE ?)"
            params += [f"%{query.strip().lower()}%", f"%{query.strip().upper()}%"]
        sql += " ORDER BY pl.name LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"id": r["id"], "product_id": r["product_id"],
                 "product_code": r["product_code"], "product_name": r["product_name"],
                 "branch_id": r["branch_id"], "sale_price": r["sale_price"],
                 "currency": r["sale_price_currency"], "min_price": r["min_price"],
                 "list_code": r["list_code"], "list_name": r["list_name"]} for r in rows]

    # ── costs ───────────────────────────────────────────────────────────────
    def list_costs(self, *, limit: int = 200) -> list[dict]:
        has_products = self._table_exists("products")
        name_sel = "p.code AS product_code, p.name AS product_name" if has_products \
            else "NULL AS product_code, NULL AS product_name"
        join = "LEFT JOIN products p ON p.id = pc.product_id" if has_products else ""
        rows = self._conn.execute(
            f"SELECT pc.product_id, {name_sel}, pc.average_cost, pc.average_cost_currency, "
            f"pc.last_cost, pc.standard_cost, pc.cost_method "
            f"FROM product_cost pc {join} ORDER BY pc.updated_at DESC LIMIT ?",
            (int(limit),)).fetchall()
        return [{"product_id": r["product_id"], "product_code": r["product_code"],
                 "product_name": r["product_name"], "average_cost": r["average_cost"],
                 "currency": r["average_cost_currency"], "last_cost": r["last_cost"],
                 "standard_cost": r["standard_cost"], "cost_method": r["cost_method"]}
                for r in rows]

    # ── price change history / audit ────────────────────────────────────────
    def list_price_history(self, *, product_id: str | None = None, limit: int = 100
                           ) -> list[dict]:
        sql = ("SELECT product_id, field, old_value, new_value, currency, user_id, "
               "authorized_by, created_at FROM price_change_log WHERE 1=1")
        params: list = []
        if product_id:
            sql += " AND product_id=?"
            params.append(product_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(int(limit))
        rows = self._conn.execute(sql, params).fetchall()
        return [{"product_id": r["product_id"], "field": r["field"],
                 "old_value": r["old_value"], "new_value": r["new_value"],
                 "currency": r["currency"], "user_id": r["user_id"],
                 "authorized_by": r["authorized_by"], "created_at": r["created_at"]}
                for r in rows]

    # ── helpers ─────────────────────────────────────────────────────────────
    def _table_exists(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone() is not None
