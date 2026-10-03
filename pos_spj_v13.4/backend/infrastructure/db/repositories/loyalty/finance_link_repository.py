"""Repositorio del puente Fidelidad → Finanzas (2026-10-03).

Lee los libros de origen (puntos, vales, canjes de cupón, premios de sorteo)
y guarda el estado de lo ya asentado. Un libro ausente (base sin ese contexto
todavía) se lee como vacío: el puente no inventa tablas ajenas.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LoyaltyFinanceLinkRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    def schema_ready(self) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='loyalty_finance_links'"
        ).fetchone() is not None

    # ── helpers ───────────────────────────────────────────────────────────
    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cursor = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def _row(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._rows(sql, params)
        return rows[0] if rows else None

    # ── links ─────────────────────────────────────────────────────────────
    def link(self, source_key: str) -> dict | None:
        return self._row("SELECT * FROM loyalty_finance_links WHERE source_key=?", (source_key,))

    def save_link(self, source_key: str, source_type: str, source_id: str, status: str, *,
                  amount: Decimal | str = "0", detail: str = "") -> None:
        ahora = _now()
        self._conn.execute(
            "INSERT INTO loyalty_finance_links (source_key, source_type, source_id, status,"
            " amount, detail, attempts, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)"
            " ON CONFLICT(source_key) DO UPDATE SET status=excluded.status,"
            " amount=excluded.amount, detail=excluded.detail,"
            " attempts=loyalty_finance_links.attempts+1, updated_at=excluded.updated_at",
            (source_key, source_type, source_id, status, str(amount), detail[:500],
             ahora, ahora))

    def failed_count(self) -> int:
        row = self._row("SELECT COUNT(*) AS n FROM loyalty_finance_links WHERE status='FAILED'")
        return int(row["n"]) if row else 0

    def failures(self, limit: int = 50) -> list[dict]:
        return self._rows(
            "SELECT source_type, source_id, detail, attempts, updated_at"
            " FROM loyalty_finance_links WHERE status='FAILED'"
            " ORDER BY updated_at DESC LIMIT ?", (limit,))

    # ── libro de puntos ───────────────────────────────────────────────────
    _TXN = ("SELECT t.id, t.loyalty_account_id, t.transaction_type, t.points_amount, t.status,"
            " t.operation_id, t.source_module, t.source_document_type, t.source_document_id,"
            " t.sale_id, t.branch_id, t.reason_code, t.expires_at, t.created_at,"
            " a.customer_id FROM loyalty_transactions t"
            " LEFT JOIN loyalty_accounts a ON a.id = t.loyalty_account_id")

    def pending_point_transactions(self, limit: int) -> list[dict]:
        return self._rows(
            self._TXN + " LEFT JOIN loyalty_finance_links l ON l.source_key = 'points:' || t.id"
            " WHERE l.source_key IS NULL OR l.status IN ('HELD','FAILED')"
            " ORDER BY t.created_at, t.id LIMIT ?", (limit,))

    def point_transaction(self, transaction_id: str) -> dict | None:
        return self._row(self._TXN + " WHERE t.id=?", (transaction_id,))

    def reversed_original(self, reversal_id: str) -> dict | None:
        return self._row(self._TXN + " WHERE t.reversal_transaction_id=?", (reversal_id,))

    # ── acumulaciones y consumos (FIFO) ───────────────────────────────────
    def save_credit(self, credit_id: str, account_id: str, points: Decimal,
                    unit_value: Decimal, amount: Decimal, created_at: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO loyalty_finance_point_credits (credit_transaction_id,"
            " loyalty_account_id, points, unit_value, amount, credit_created_at)"
            " VALUES (?,?,?,?,?,?)",
            (credit_id, account_id, str(points), str(unit_value), str(amount), created_at))

    _CREDITS = ("SELECT credit_transaction_id, loyalty_account_id, points, unit_value, amount,"
                " credit_created_at FROM loyalty_finance_point_credits")

    def credit(self, credit_id: str) -> dict | None:
        return self._row(self._CREDITS + " WHERE credit_transaction_id=?", (credit_id,))

    def credits_for_account(self, account_id: str) -> list[dict]:
        return self._rows(self._CREDITS + " WHERE loyalty_account_id=?"
                          " ORDER BY credit_created_at, credit_transaction_id", (account_id,))

    def active_allocations_for_credit(self, credit_id: str) -> list[dict]:
        return self._rows(
            "SELECT * FROM loyalty_finance_point_allocations"
            " WHERE credit_transaction_id=? AND status='ACTIVE'", (credit_id,))

    def allocations_for_debit(self, debit_id: str, *, kinds: tuple[str, ...] = ()) -> list[dict]:
        sql = ("SELECT * FROM loyalty_finance_point_allocations"
               " WHERE debit_transaction_id=? AND status='ACTIVE'")
        params: tuple = (debit_id,)
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += tuple(kinds)
        return self._rows(sql + " ORDER BY created_at, id", params)

    def add_allocation(self, debit_id: str, credit_id: str, points: Decimal, amount: Decimal,
                       kind: str) -> str:
        allocation_id = new_uuid()
        self._conn.execute(
            "INSERT INTO loyalty_finance_point_allocations (id, debit_transaction_id,"
            " credit_transaction_id, points, amount, kind, status, created_at)"
            " VALUES (?,?,?,?,?,?, 'ACTIVE', ?)",
            (allocation_id, debit_id, credit_id, str(points), str(amount), kind, _now()))
        return allocation_id

    def set_allocation_kind(self, allocation_id: str, kind: str) -> None:
        self._conn.execute("UPDATE loyalty_finance_point_allocations SET kind=? WHERE id=?",
                           (kind, allocation_id))

    def void_allocation(self, allocation_id: str) -> None:
        self._conn.execute(
            "UPDATE loyalty_finance_point_allocations SET status='VOID' WHERE id=?",
            (allocation_id,))

    # ── vales ─────────────────────────────────────────────────────────────
    _VOUCHER = ("SELECT t.id, t.voucher_instance_id, t.transaction_type, t.amount, t.status,"
                " t.sale_id, t.created_at, i.customer_id, i.expires_at, i.status AS instance_status,"
                " d.voucher_type FROM voucher_transactions t"
                " JOIN voucher_instances i ON i.id = t.voucher_instance_id"
                " JOIN voucher_definitions d ON d.id = i.definition_id")

    def pending_voucher_transactions(self, limit: int) -> list[dict]:
        return self._rows(
            self._VOUCHER + " LEFT JOIN loyalty_finance_links l ON l.source_key = 'voucher:' || t.id"
            " WHERE l.source_key IS NULL OR l.status IN ('HELD','FAILED')"
            " ORDER BY t.created_at, t.id LIMIT ?", (limit,))

    def voucher_transaction(self, transaction_id: str) -> dict | None:
        return self._row(self._VOUCHER + " WHERE t.id=?", (transaction_id,))

    def voucher_reversed_original(self, reversal_id: str) -> dict | None:
        return self._row(self._VOUCHER + " WHERE t.reversal_transaction_id=?", (reversal_id,))

    def closed_voucher_instances(self) -> list[dict]:
        return self._rows(
            "SELECT i.id, i.status, d.voucher_type FROM voucher_instances i"
            " JOIN voucher_definitions d ON d.id = i.definition_id"
            " LEFT JOIN loyalty_finance_links l ON l.source_key = 'voucher-close:' || i.id"
            " WHERE i.status IN ('CANCELLED','EXPIRED')"
            " AND (l.source_key IS NULL OR l.status = 'FAILED')")

    # ── cupones ───────────────────────────────────────────────────────────
    def pending_coupon_redemptions(self, limit: int) -> list[dict]:
        return self._rows(
            "SELECT r.id, r.coupon_instance_id, r.sale_id, r.amount_applied, r.redeemed_at,"
            " d.coupon_type, i.customer_id FROM coupon_redemptions r"
            " JOIN coupon_instances i ON i.id = r.coupon_instance_id"
            " JOIN coupon_definitions d ON d.id = i.definition_id"
            " LEFT JOIN loyalty_finance_links l ON l.source_key = 'coupon:' || r.id"
            " WHERE l.source_key IS NULL OR l.status = 'FAILED'"
            " ORDER BY r.redeemed_at, r.id LIMIT ?", (limit,))

    # ── sorteos ───────────────────────────────────────────────────────────
    def prizes_to_provision(self) -> list[dict]:
        return self._rows(
            "SELECT p.id, p.campaign_id, p.name, p.quantity, p.estimated_cost,"
            " c.branch_id, c.status AS campaign_status, c.name AS campaign_name"
            " FROM sweepstakes_prizes p JOIN sweepstakes_campaigns c ON c.id = p.campaign_id"
            " LEFT JOIN loyalty_finance_links l ON l.source_key = 'prize:' || p.id"
            " WHERE c.status IN ('ACTIVE','PAUSED','DRAWN','CLOSED')"
            " AND (l.source_key IS NULL OR l.status = 'FAILED')")

    def delivered_winners(self) -> list[dict]:
        return self._rows(
            "SELECT w.id, w.prize_id, w.campaign_id, w.customer_id, w.delivered_at,"
            " p.estimated_cost FROM sweepstakes_winners w"
            " JOIN sweepstakes_prizes p ON p.id = w.prize_id"
            " LEFT JOIN loyalty_finance_links l ON l.source_key = 'winner:' || w.id"
            " WHERE w.status = 'PRIZE_DELIVERED' AND w.prize_id IS NOT NULL"
            " AND (l.source_key IS NULL OR l.status = 'FAILED')")

    def prizes_to_release(self) -> list[dict]:
        """Premios provisionados de campañas ya resueltas: cancelada, o
        sorteada/cerrada sin sorteo pendiente ni ganador por validar o entregar."""
        return self._rows(
            "SELECT p.id, p.campaign_id, c.status AS campaign_status"
            " FROM sweepstakes_prizes p JOIN sweepstakes_campaigns c ON c.id = p.campaign_id"
            " JOIN loyalty_finance_links lp ON lp.source_key = 'prize:' || p.id"
            "   AND lp.status = 'POSTED'"
            " LEFT JOIN loyalty_finance_links l ON l.source_key = 'prize-release:' || p.id"
            " WHERE (l.source_key IS NULL OR l.status = 'FAILED') AND ("
            "   c.status = 'CANCELLED' OR (c.status IN ('DRAWN','CLOSED')"
            "   AND NOT EXISTS (SELECT 1 FROM sweepstakes_draws d WHERE d.campaign_id = c.id"
            "                   AND d.status = 'SCHEDULED')"
            "   AND NOT EXISTS (SELECT 1 FROM sweepstakes_winners w WHERE w.prize_id = p.id"
            "                   AND w.status IN ('PENDING_VALIDATION','VALIDATED'))"
            "   AND NOT EXISTS (SELECT 1 FROM sweepstakes_winners w"
            "                   JOIN loyalty_finance_links lw ON lw.source_key = 'winner:' || w.id"
            "                   WHERE w.prize_id = p.id AND w.status = 'PRIZE_DELIVERED'"
            "                   AND lw.status <> 'POSTED')"
            "   AND NOT EXISTS (SELECT 1 FROM sweepstakes_winners w"
            "                   LEFT JOIN loyalty_finance_links lw ON lw.source_key = 'winner:' || w.id"
            "                   WHERE w.prize_id = p.id AND w.status = 'PRIZE_DELIVERED'"
            "                   AND lw.source_key IS NULL)))")


__all__ = ["LoyaltyFinanceLinkRepository"]
