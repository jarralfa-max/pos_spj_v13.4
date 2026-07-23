"""BranchAssortmentRepository — persistence for branch products / assortments (PROD-14).

One product, many branch rows (never duplicated). No price/stock columns.
Never commits (the caller owns the transaction). Parametrized queries only.
"""

from __future__ import annotations

from backend.domain.products.channel_enums import SalesChannel
from backend.domain.products.entities.assortment import Assortment, AssortmentProduct
from backend.domain.products.entities.branch_product import BranchProduct


class BranchAssortmentRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── branch product ────────────────────────────────────────────────────
    def set_branch_product(self, bp: BranchProduct) -> None:
        self._conn.execute(
            """INSERT INTO branch_product (id, product_id, branch_id, enabled, notes)
               VALUES (?,?,?,?,?)
               ON CONFLICT(product_id, branch_id) DO UPDATE SET
                 enabled=excluded.enabled, notes=excluded.notes""",
            (bp.id, bp.product_id, bp.branch_id, int(bp.enabled), bp.notes))

    def is_enabled_at_branch(self, product_id: str, branch_id: str) -> bool:
        row = self._conn.execute(
            "SELECT enabled FROM branch_product WHERE product_id=? AND branch_id=?",
            (product_id, branch_id)).fetchone()
        return bool(row["enabled"]) if row else False

    def products_at_branch(self, branch_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT product_id FROM branch_product WHERE branch_id=? AND enabled=1",
            (branch_id,)).fetchall()
        return [r["product_id"] for r in rows]

    # ── assortments ───────────────────────────────────────────────────────
    def save_assortment(self, a: Assortment) -> None:
        self._conn.execute(
            """INSERT INTO assortments (id, name, channel, branch_id, active)
               VALUES (?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                 channel=excluded.channel, branch_id=excluded.branch_id,
                 active=excluded.active""",
            (a.id, a.name, a.channel.value, a.branch_id, int(a.active)))

    def get_assortment(self, assortment_id: str) -> Assortment | None:
        row = self._conn.execute(
            "SELECT * FROM assortments WHERE id=?", (assortment_id,)).fetchone()
        if row is None:
            return None
        return Assortment(id=row["id"], name=row["name"],
                          channel=SalesChannel(row["channel"]),
                          branch_id=row["branch_id"], active=bool(row["active"]))

    def add_to_assortment(self, item: AssortmentProduct) -> None:
        self._conn.execute(
            """INSERT INTO assortment_products (id, assortment_id, product_id, enabled)
               VALUES (?,?,?,?)
               ON CONFLICT(assortment_id, product_id) DO UPDATE SET
                 enabled=excluded.enabled""",
            (item.id, item.assortment_id, item.product_id, int(item.enabled)))

    def products_in_assortment(self, assortment_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT product_id FROM assortment_products "
            "WHERE assortment_id=? AND enabled=1", (assortment_id,)).fetchall()
        return [r["product_id"] for r in rows]
