"""CanonicalStockReadAdapter — strangler read facade for the cutover (INV-27).

Lets legacy availability readers be repointed to the canonical projection one at a
time, safely. It reads ``inventory_balances`` (canonical, Decimal) and:

- if the canonical cutover flag is ON → canonical is authoritative (no fallback);
- else, during transition → returns canonical when a balance row exists for the
  product, otherwise falls back to the injected legacy callable.

This is the seam that keeps the POS working while stock is being backfilled and
readers migrated. It lives in the legacy ``core`` layer (float↔Decimal bridging is
allowed here); the canonical context stays Decimal-only.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.cutover import is_cutover_enabled
from backend.application.inventory.queries import InventoryAvailabilityQueryService


def _dec(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class CanonicalStockReadAdapter:
    def __init__(self, connection_provider, *, legacy_available=None, env=None) -> None:
        self._conn = connection_provider
        self._legacy_available = legacy_available
        self._env = env

    def available(self, product_id, branch_id=None) -> Decimal:
        conn = self._conn()
        canonical, found = self._canonical(conn, str(product_id),
                                           None if branch_id is None else str(branch_id))
        if found or is_cutover_enabled(conn, env=self._env):
            return canonical
        if self._legacy_available is not None:
            return _dec(self._legacy_available(product_id, branch_id))
        return canonical

    def available_float(self, product_id, branch_id=None) -> float:
        """Compat shim for legacy callers that expect a float."""
        return float(self.available(product_id, branch_id))

    # ── internals ────────────────────────────────────────────────────────────
    def _canonical(self, conn, product_id: str, branch_id: str | None):
        """Return (available, found). ``found`` is True when the canonical
        projection has any AVAILABLE row for this product (± branch)."""
        if branch_id is not None:
            dto = InventoryAvailabilityQueryService(conn).get_availability(
                product_id=product_id, branch_id=branch_id)
            found = self._has_row(conn, product_id, branch_id)
            return dto.available, found
        # no branch → total available across branches
        rows = self._query(
            conn,
            "SELECT quantity, reserved_quantity FROM inventory_balances"
            " WHERE product_id=? AND inventory_status='AVAILABLE'", (product_id,))
        total = Decimal("0")
        for r in rows:
            total += _dec(r[0]) - _dec(r[1])
        return total, bool(rows)

    def _has_row(self, conn, product_id: str, branch_id: str) -> bool:
        return bool(self._query(
            conn,
            "SELECT 1 FROM inventory_balances WHERE product_id=? AND branch_id=?"
            " AND inventory_status='AVAILABLE' LIMIT 1", (product_id, branch_id)))

    @staticmethod
    def _query(conn, sql: str, params: tuple):
        return conn.execute(sql, params).fetchall()
