"""PricingRepository — persistence for lists / prices / costs (PRC-4).

Money ↔ (amount TEXT, currency TEXT); branch scope uses '' for "all branches"
(mapped to None on the entity). Never commits (the caller owns the transaction).
Parametrized queries only.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.pricing.entities.price_list import PriceList
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.entities.product_price import ProductPrice, VolumePrice
from backend.domain.pricing.enums import CostMethod, PriceListKind, PriceListStatus
from backend.domain.pricing.value_objects.money import Money
from backend.shared.ids import new_uuid


def _money(amount: str | None, currency: str | None) -> Money | None:
    if amount is None:
        return None
    return Money(Decimal(amount), currency or "MXN")


class PricingRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── price list ────────────────────────────────────────────────────────
    def save_list(self, pl: PriceList) -> None:
        self._conn.execute(
            """INSERT INTO price_list (id, code, name, kind, status, channel,
                discount_pct, inherits_from_id, approved_by_user_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?, datetime('now'))
               ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                 discount_pct=excluded.discount_pct,
                 approved_by_user_id=excluded.approved_by_user_id,
                 updated_at=datetime('now')""",
            (pl.id, pl.code, pl.name, pl.kind.value, pl.status.value, pl.channel,
             str(pl.discount_pct), pl.inherits_from_id, pl.approved_by_user_id))

    def get_list(self, list_id: str) -> PriceList | None:
        row = self._conn.execute("SELECT * FROM price_list WHERE id=?", (list_id,)).fetchone()
        return self._row_to_list(row) if row else None

    def active_list_of_kind(self, kind: PriceListKind) -> PriceList | None:
        row = self._conn.execute(
            "SELECT * FROM price_list WHERE kind=? AND status='ACTIVE' "
            "ORDER BY updated_at DESC LIMIT 1", (kind.value,)).fetchone()
        return self._row_to_list(row) if row else None

    @staticmethod
    def _row_to_list(row) -> PriceList:
        return PriceList(id=row["id"], code=row["code"], name=row["name"],
                         kind=PriceListKind(row["kind"]),
                         status=PriceListStatus(row["status"]), channel=row["channel"],
                         discount_pct=Decimal(row["discount_pct"]),
                         inherits_from_id=row["inherits_from_id"],
                         approved_by_user_id=row["approved_by_user_id"])

    # ── product price ─────────────────────────────────────────────────────
    def save_price(self, pp: ProductPrice) -> None:
        self._conn.execute(
            """INSERT INTO product_price (id, price_list_id, product_id, branch_id,
                sale_price, sale_price_currency, min_price, min_price_currency,
                effective_from, effective_to)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(price_list_id, product_id, branch_id) DO UPDATE SET
                 sale_price=excluded.sale_price,
                 sale_price_currency=excluded.sale_price_currency,
                 min_price=excluded.min_price, min_price_currency=excluded.min_price_currency""",
            (pp.id, pp.price_list_id, pp.product_id, pp.branch_id or "",
             str(pp.sale_price.amount), pp.sale_price.currency,
             None if pp.min_price is None else str(pp.min_price.amount),
             None if pp.min_price is None else pp.min_price.currency,
             pp.effective_from, pp.effective_to))

    def get_price(self, *, price_list_id: str, product_id: str, branch_id: str | None
                  ) -> ProductPrice | None:
        """Branch-specific price first, then the all-branches ('') fallback."""
        row = None
        if branch_id:
            row = self._conn.execute(
                "SELECT * FROM product_price WHERE price_list_id=? AND product_id=? "
                "AND branch_id=?", (price_list_id, product_id, branch_id)).fetchone()
        if row is None:
            row = self._conn.execute(
                "SELECT * FROM product_price WHERE price_list_id=? AND product_id=? "
                "AND branch_id=''", (price_list_id, product_id)).fetchone()
        return self._row_to_price(row) if row else None

    @staticmethod
    def _row_to_price(row) -> ProductPrice:
        return ProductPrice(
            id=row["id"], price_list_id=row["price_list_id"], product_id=row["product_id"],
            branch_id=row["branch_id"] or None,
            sale_price=_money(row["sale_price"], row["sale_price_currency"]),
            min_price=_money(row["min_price"], row["min_price_currency"]),
            effective_from=row["effective_from"], effective_to=row["effective_to"])

    # ── volume price ──────────────────────────────────────────────────────
    def save_volume(self, v: VolumePrice) -> None:
        self._conn.execute(
            "INSERT INTO volume_price (id, product_price_id, min_quantity, price, "
            "price_currency) VALUES (?,?,?,?,?)",
            (v.id, v.product_price_id, str(v.min_quantity), str(v.price.amount),
             v.price.currency))

    def volume_tiers(self, product_price_id: str) -> list[VolumePrice]:
        rows = self._conn.execute(
            "SELECT * FROM volume_price WHERE product_price_id=? ORDER BY min_quantity",
            (product_price_id,)).fetchall()
        return [VolumePrice(id=r["id"], product_price_id=r["product_price_id"],
                            min_quantity=Decimal(r["min_quantity"]),
                            price=_money(r["price"], r["price_currency"])) for r in rows]

    # ── customer list ─────────────────────────────────────────────────────
    def assign_customer_list(self, customer_id: str, price_list_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO customer_price_list (customer_id, price_list_id) "
            "VALUES (?,?)", (customer_id, price_list_id))

    def customer_list_id(self, customer_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT cpl.price_list_id FROM customer_price_list cpl "
            "JOIN price_list pl ON pl.id = cpl.price_list_id "
            "WHERE cpl.customer_id=? AND pl.status='ACTIVE' LIMIT 1",
            (customer_id,)).fetchone()
        return row["price_list_id"] if row else None

    # ── product cost ──────────────────────────────────────────────────────
    def save_cost(self, c: ProductCost) -> None:
        self._conn.execute(
            """INSERT INTO product_cost (id, product_id, branch_id, average_cost,
                average_cost_currency, last_cost, standard_cost, cost_method, effective_from)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(product_id, branch_id) DO UPDATE SET
                 average_cost=excluded.average_cost, last_cost=excluded.last_cost,
                 standard_cost=excluded.standard_cost, cost_method=excluded.cost_method,
                 updated_at=datetime('now')""",
            (c.id, c.product_id, c.branch_id or "", str(c.average_cost.amount),
             c.average_cost.currency,
             None if c.last_cost is None else str(c.last_cost.amount),
             None if c.standard_cost is None else str(c.standard_cost.amount),
             c.cost_method.value, c.effective_from))

    def cost_basis(self, product_id: str, branch_id: str = "") -> tuple[Money | None, Decimal]:
        """Prior (average_cost, tracked_quantity) used by the moving average."""
        row = self._conn.execute(
            "SELECT average_cost, average_cost_currency, tracked_quantity FROM product_cost "
            "WHERE product_id=? AND branch_id=?", (product_id, branch_id)).fetchone()
        if row is None:
            return None, Decimal("0")
        avg = _money(row["average_cost"], row["average_cost_currency"])
        qty = Decimal(row["tracked_quantity"]) if row["tracked_quantity"] else Decimal("0")
        return avg, qty

    def upsert_cost_basis(self, *, product_id: str, branch_id: str, average: Money,
                          last: Money, tracked_quantity: Decimal) -> None:
        self._conn.execute(
            """INSERT INTO product_cost (id, product_id, branch_id, average_cost,
                average_cost_currency, last_cost, cost_method, tracked_quantity)
               VALUES (?,?,?,?,?,?, 'AVERAGE', ?)
               ON CONFLICT(product_id, branch_id) DO UPDATE SET
                 average_cost=excluded.average_cost,
                 average_cost_currency=excluded.average_cost_currency,
                 last_cost=excluded.last_cost,
                 tracked_quantity=excluded.tracked_quantity,
                 updated_at=datetime('now')""",
            (new_uuid(), product_id, branch_id or "", str(average.amount), average.currency,
             str(last.amount), str(tracked_quantity)))

    def cost_change_applied(self, product_id: str, operation_id: str) -> bool:
        """Idempotency: a cost change already logged for this (product, event)."""
        return self._conn.execute(
            "SELECT 1 FROM price_change_log WHERE product_id=? AND field='cost' "
            "AND operation_id=? LIMIT 1", (product_id, operation_id)).fetchone() is not None

    def log_cost_change(self, *, product_id: str, branch_id: str | None, old_value: Money | None,
                        new_value: Money, operation_id: str, user_id: str | None = None) -> None:
        self._conn.execute(
            """INSERT INTO price_change_log (id, product_id, branch_id, field, old_value,
                new_value, currency, user_id, operation_id)
               VALUES (?,?,?, 'cost', ?,?,?,?,?)""",
            (new_uuid(), product_id, branch_id or None,
             None if old_value is None else str(old_value.amount),
             str(new_value.amount), new_value.currency, user_id, operation_id))

    def enqueue_event(self, *, event_id: str, event_name: str, operation_id: str | None,
                      entity_id: str | None, payload: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO pricing_outbox (id, event_id, event_name, operation_id, "
            "entity_id, payload) VALUES (?,?,?,?,?,?)",
            (new_uuid(), event_id, event_name, operation_id, entity_id, payload))

    def get_cost(self, product_id: str, branch_id: str | None = None) -> ProductCost | None:
        row = None
        if branch_id:
            row = self._conn.execute(
                "SELECT * FROM product_cost WHERE product_id=? AND branch_id=?",
                (product_id, branch_id)).fetchone()
        if row is None:
            row = self._conn.execute(
                "SELECT * FROM product_cost WHERE product_id=? AND branch_id=''",
                (product_id,)).fetchone()
        if row is None:
            return None
        return ProductCost(
            id=row["id"], product_id=row["product_id"], branch_id=row["branch_id"] or None,
            average_cost=_money(row["average_cost"], row["average_cost_currency"]),
            last_cost=_money(row["last_cost"], row["average_cost_currency"]),
            standard_cost=_money(row["standard_cost"], row["average_cost_currency"]),
            cost_method=CostMethod(row["cost_method"]), effective_from=row["effective_from"])
