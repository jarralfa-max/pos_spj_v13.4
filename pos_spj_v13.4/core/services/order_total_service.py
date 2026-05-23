from __future__ import annotations


class OrderTotalService:
    """Single source of truth for recalculating delivery/sale totals."""

    def __init__(self, db):
        self.db = db

    def recalculate_order_total(self, order_id: int) -> float:
        row = self.db.execute(
            "SELECT COALESCE(SUM(subtotal), 0) FROM delivery_items WHERE delivery_id=?",
            (order_id,),
        ).fetchone()
        new_total = round(float(row[0]) if row else 0.0, 2)

        cols = {r[1] for r in self.db.execute("PRAGMA table_info(delivery_orders)").fetchall()}
        if "weight_adjusted" in cols:
            self.db.execute(
                "UPDATE delivery_orders SET total=?, weight_adjusted=1 WHERE id=?",
                (new_total, order_id),
            )
        else:
            self.db.execute(
                "UPDATE delivery_orders SET total=? WHERE id=?",
                (new_total, order_id),
            )

        venta_row = self.db.execute("SELECT venta_id FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        if venta_row and venta_row[0]:
            self.db.execute("UPDATE ventas SET total=? WHERE id=?", (new_total, int(venta_row[0])))

        self.db.commit()
        return new_total
