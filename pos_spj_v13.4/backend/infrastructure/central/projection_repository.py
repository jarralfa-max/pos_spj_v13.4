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

    # ── Caja (Slice 6) ──────────────────────────────────────────────────
    def open_cash_shift(self, row: dict) -> None:
        self._exec(
            """INSERT INTO central_cash_shifts (shift_id, event_id, branch_id, station_id,
               register_id, cashier_user_id, opening_amount, opened_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (shift_id) DO NOTHING""",
            (row["shift_id"], row["event_id"], row["branch_id"], row["station_id"],
             row["register_id"], row["cashier_user_id"], row["opening_amount"],
             row["opened_at"]))

    def close_cash_shift(self, *, shift_id: str, closed_at, z_cut_id) -> None:
        self._exec("UPDATE central_cash_shifts SET status = 'CLOSED', closed_at = %s,"
                   " z_cut_id = COALESCE(%s, z_cut_id) WHERE shift_id = %s",
                   (closed_at, z_cut_id, shift_id))

    def add_cash_movement(self, row: dict) -> None:
        self._exec(
            """INSERT INTO central_cash_movements (movement_id, event_id, branch_id, shift_id,
               movement_kind, signed_amount, reversal_of_id, sale_id, occurred_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (movement_id) DO NOTHING""",
            (row["movement_id"], row["event_id"], row["branch_id"], row["shift_id"],
             row["movement_kind"], row["signed_amount"], row["reversal_of_id"], row["sale_id"],
             row["occurred_at"]))

    def cash_movement_signed(self, movement_id: str):
        with self._conn.cursor() as cur:
            cur.execute("SELECT signed_amount FROM central_cash_movements WHERE movement_id = %s",
                        (movement_id,))
            fila = cur.fetchone()
        return None if fila is None else fila[0]

    def add_cash_cut(self, row: dict) -> None:
        self._exec(
            """INSERT INTO central_cash_cuts (cut_id, event_id, branch_id, shift_id,
               document_number, expected_cash, counted_cash, difference, business_date,
               occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (cut_id) DO NOTHING""",
            (row["cut_id"], row["event_id"], row["branch_id"], row["shift_id"],
             row["document_number"], row["expected_cash"], row["counted_cash"],
             row["difference"], row["business_date"], row["occurred_at"]))

    # ── Finanzas (Slice 6) ──────────────────────────────────────────────
    def add_journal_entry(self, rows: dict) -> None:
        a = rows["entry"]
        insertado = self._exec(
            """INSERT INTO central_journal_entries (entry_id, event_id, branch_id, entry_number,
               entry_date, posting_date, source_module, source_document_ref, posting_purpose,
               currency_code, base_currency_code, total_debits, total_credits,
               reversal_of_entry_id, occurred_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (entry_id) DO NOTHING""",
            (a["entry_id"], a["event_id"], a["branch_id"], a["entry_number"], a["entry_date"],
             a["posting_date"], a["source_module"], a["source_document_ref"],
             a["posting_purpose"], a["currency_code"], a["base_currency_code"],
             a["total_debits"], a["total_credits"], a["reversal_of_entry_id"],
             a["occurred_at"]))
        if not insertado:
            return
        for l in rows["lines"]:
            self._exec(
                """INSERT INTO central_journal_lines (entry_id, line_index, account_code,
                   account_type, is_receivable, debit, credit, line_role, line_branch_id,
                   cost_center_id, customer_id, supplier_id, product_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (a["entry_id"], l["line_index"], l["account_code"], l["account_type"],
                 l["is_receivable"], l["debit"], l["credit"], l["line_role"],
                 l["line_branch_id"], l["cost_center_id"], l["customer_id"], l["supplier_id"],
                 l["product_id"]))

    # ── Crédito (Slice 6) ───────────────────────────────────────────────
    def upsert_credit_account(self, row: dict) -> None:
        self._exec(
            """INSERT INTO central_credit_accounts (profile_id, customer_id, branch_id,
               credit_limit, status, last_event_id, updated_at)
               VALUES (%s,%s,%s,COALESCE(%s, 0),COALESCE(%s, 'ACTIVE'),%s,%s)
               ON CONFLICT (profile_id) DO UPDATE SET
                 credit_limit = COALESCE(%s, central_credit_accounts.credit_limit),
                 status = COALESCE(%s, central_credit_accounts.status),
                 last_event_id = EXCLUDED.last_event_id, updated_at = EXCLUDED.updated_at""",
            (row["profile_id"], row["customer_id"], row["branch_id"], row["credit_limit"],
             row["status"], row["event_id"], row["occurred_at"], row["credit_limit"],
             row["status"]))

    # ── Fidelidad (Slice 6) ─────────────────────────────────────────────
    def upsert_loyalty_transaction(self, row: dict) -> None:
        """Una fila por TRANSACCIÓN: un evento posterior de la misma transacción
        (p. ej. confirmar la reserva) actualiza su estado, no suma otra vez."""
        self._exec(
            """INSERT INTO central_loyalty_transactions (transaction_id, first_event_id,
               last_event_id, loyalty_account_id, customer_id, membership_id, branch_id,
               transaction_type, status, points_amount, counts_toward_balance, sale_id,
               updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (transaction_id) DO UPDATE SET
                 last_event_id = EXCLUDED.last_event_id, status = EXCLUDED.status,
                 points_amount = EXCLUDED.points_amount,
                 counts_toward_balance = EXCLUDED.counts_toward_balance,
                 updated_at = EXCLUDED.updated_at""",
            (row["transaction_id"], row["event_id"], row["event_id"],
             row["loyalty_account_id"], row["customer_id"], row["membership_id"],
             row["branch_id"], row["transaction_type"], row["status"], row["points_amount"],
             row["counts_toward_balance"], row["sale_id"], row["occurred_at"]))

    # ── Estructura organizacional (auditoría enterprise) ────────────────
    def upsert_org_unit(self, row: dict) -> None:
        """Foto completa; sólo reemplaza si es más reciente (un evento atrasado
        no deshace un cambio posterior)."""
        self._exec(
            """INSERT INTO central_org_units (unit_id, company_id, parent_id, unit_type, code,
               name, status, closed_at, capabilities, source_branch_id, last_event_id,
               updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (unit_id) DO UPDATE SET
                 parent_id = EXCLUDED.parent_id, unit_type = EXCLUDED.unit_type,
                 code = EXCLUDED.code, name = EXCLUDED.name, status = EXCLUDED.status,
                 closed_at = EXCLUDED.closed_at, capabilities = EXCLUDED.capabilities,
                 source_branch_id = EXCLUDED.source_branch_id,
                 last_event_id = EXCLUDED.last_event_id, updated_at = EXCLUDED.updated_at
               WHERE central_org_units.updated_at <= EXCLUDED.updated_at""",
            (row["unit_id"], row["company_id"], row["parent_id"], row["unit_type"],
             row["code"], row["name"], row["status"], row["closed_at"], row["capabilities"],
             row["source_branch_id"], row["event_id"], row["updated_at"]))


__all__ = ["PostgresCentralProjectionRepository"]
