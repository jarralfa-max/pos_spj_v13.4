"""Read services migrated from the legacy monolith: purchase templates and the
canonical purchase cost of a product.

- Purchase templates: replaces `ComprasReadRepository.list_purchase_templates /
  get_template_items` used by the sidebar in `compras_pro.py`. The new UI loads a
  template's lines into the cart through the presenter.
- Historical cost reads `product_cost.average_cost`. Returned as a Decimal string so the domain
  PriceVariancePolicy can compare without float.

Both tolerate missing tables (fresh dev DB) → empty / "0".
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any


class _Base:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cur = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _scalar(self, sql: str, params: tuple = (), default=None):
        try:
            row = self._conn.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return default
        return row[0] if row and row[0] is not None else default


class PurchaseTemplateReadService(_Base):
    def list_templates(self, *, limit: int = 20) -> list[dict]:
        return self._rows(
            "SELECT id, nombre AS name, COALESCE(descripcion,'') AS description,"
            " COALESCE(proveedor_id,'') AS supplier_id"
            " FROM plantillas_compra WHERE COALESCE(activo,1)=1"
            " ORDER BY nombre LIMIT ?", (int(limit),))

    def template_lines(self, template_id: str) -> list[dict]:
        """Template items as cart-ready line dicts (product_id, quantity, unit_cost)."""
        rows = self._rows(
            "SELECT producto_id AS product_id, cantidad AS quantity,"
            " COALESCE(costo_unitario,0) AS unit_cost"
            " FROM plantillas_compra_items WHERE plantilla_id=? ORDER BY id",
            (template_id,))
        return [{"product_id": str(r["product_id"]),
                 "quantity": str(r["quantity"] or "0"),
                 "unit_cost": str(r["unit_cost"] or "0")} for r in rows]


class ProductPurchaseCostReadService(_Base):
    """Historical purchase cost of a product for the variance check.

    The canonical `product_cost` projection is the only cost source.
    """

    def historical_cost(self, product_id: str, *, branch_id: str | None = None) -> str:
        branch = branch_id or ""
        value = self._scalar(
            "SELECT average_cost FROM product_cost WHERE product_id=? AND branch_id=?",
            (product_id, branch))
        if value is None and branch:
            value = self._scalar(
                "SELECT average_cost FROM product_cost WHERE product_id=? AND branch_id=''",
                (product_id,))
        try:
            amount = Decimal(str(value or "0"))
        except InvalidOperation:
            return "0"
        return str(amount) if amount > Decimal("0") else "0"
