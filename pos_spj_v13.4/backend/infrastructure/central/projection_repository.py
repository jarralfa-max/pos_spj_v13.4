"""Proyecciones centrales en PostgreSQL (Slice 5). Implementa
`CentralProjectionRepository`. Todas las inserciones son idempotentes (`ON
CONFLICT DO NOTHING`): reproyectar nunca duplica una venta ni un movimiento."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Mapping


class PostgresCentralProjectionRepository:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _exec(self, sql: str, params: tuple = ()) -> int:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    @contextmanager
    def savepoint(self):
        with self._conn.transaction():
            yield

    def commit(self) -> None:
        self._conn.commit()

    def pending_facts(self, *, projector: str, limit: int) -> list[Mapping[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT i.event_id, i.event_type, i.aggregate_id, i.branch_id, i.station_id,
                          i.occurred_at, i.payload
                   FROM sync_inbox i
                   WHERE i.status = 'APPLIED'
                     AND NOT EXISTS (SELECT 1 FROM central_projection_log l
                                     WHERE l.event_id = i.event_id AND l.projector = %s)
                   ORDER BY i.received_at, i.station_id, i.sequence_no
                   LIMIT %s""", (projector, limit))
            nombres = [c.name for c in cur.description]
            return [{k: (str(v) if k in ("event_id", "aggregate_id", "branch_id", "station_id")
                         else v) for k, v in zip(nombres, fila)} for fila in cur.fetchall()]

    def log(self, *, event_id: str, projector: str, status: str, error: str | None) -> None:
        self._exec(
            """INSERT INTO central_projection_log (event_id, projector, status, error)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (event_id, projector) DO UPDATE SET status = EXCLUDED.status,
                 error = EXCLUDED.error, projected_at = now()""",
            (event_id, projector, status, error))

    def upsert_sale(self, rows: dict) -> None:
        v = rows["sale"]
        insertada = self._exec(
            """INSERT INTO central_sales (sale_id, event_id, branch_id, station_id, folio,
               customer_id, channel, currency_code, occurred_at, gross_subtotal,
               discount_total, promotion_total, coupon_total, loyalty_total, tax_total,
               rounding_adjustment, total, change_given)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (sale_id) DO NOTHING""",
            (v["sale_id"], v["event_id"], v["branch_id"], v["station_id"], v["folio"],
             v["customer_id"], v["channel"], v["currency_code"], v["occurred_at"],
             v["gross_subtotal"], v["discount_total"], v["promotion_total"], v["coupon_total"],
             v["loyalty_total"], v["tax_total"], v["rounding_adjustment"], v["total"],
             v["change_given"]))
        if not insertada:
            return
        for l in rows["lines"]:
            self._exec("INSERT INTO central_sale_lines (sale_id, line_no, product_id, quantity,"
                       " amount, unit_cost) VALUES (%s,%s,%s,%s,%s,%s)",
                       (v["sale_id"], l["line_no"], l["product_id"], l["quantity"], l["amount"],
                        l["unit_cost"]))
        for p in rows["payments"]:
            self._exec("INSERT INTO central_sale_payments (sale_id, method, amount)"
                       " VALUES (%s,%s,%s)", (v["sale_id"], p["method"], p["amount"]))

    def set_sale_status(self, *, sale_id: str, status: str, event_id: str) -> None:
        self._exec("UPDATE central_sales SET status = %s, status_event_id = %s"
                   " WHERE sale_id = %s", (status, event_id, sale_id))

    def add_sale_return(self, row: dict) -> None:
        self._exec("INSERT INTO central_sale_returns (event_id, sale_id, branch_id, amount,"
                   " occurred_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (event_id) DO NOTHING",
                   (row["event_id"], row["sale_id"], row["branch_id"], row["amount"],
                    row["occurred_at"]))

    def add_stock_movement(self, rows: dict) -> None:
        m = rows["movement"]
        insertado = self._exec(
            """INSERT INTO central_stock_movements (movement_id, event_id, branch_id,
               warehouse_id, movement_type, document_module, document_type, document_id,
               reversal_of_id, occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (movement_id) DO NOTHING""",
            (m["movement_id"], m["event_id"], m["branch_id"], m["warehouse_id"],
             m["movement_type"], m["document_module"], m["document_type"], m["document_id"],
             m["reversal_of_id"], m["occurred_at"]))
        if not insertado:
            return
        for e in rows["effects"]:
            self._exec(
                """INSERT INTO central_stock_effects (movement_id, effect_no, product_id, lot_id,
                   warehouse_id, location_id, inventory_status, quantity_delta, weight_delta)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (m["movement_id"], e["effect_no"], e["product_id"], e["lot_id"],
                 e["warehouse_id"], e["location_id"], e["inventory_status"],
                 e["quantity_delta"], e["weight_delta"]))


__all__ = ["PostgresCentralProjectionRepository"]
