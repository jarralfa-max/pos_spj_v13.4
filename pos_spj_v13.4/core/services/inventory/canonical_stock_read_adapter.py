"""CanonicalStockReadAdapter — strangler read facade for the cutover (INV-27).

Lets legacy availability readers be repointed to the canonical projection one at a
time, safely. **Reads follow writes**, gated by the cutover flag:

- flag ON  → canonical (``inventory_balances``) is authoritative; the legacy path
  has been neutralized, so canonical is the live truth.
- flag OFF → the legacy path still OWNS writes, so canonical is only a stale
  backfilled snapshot; the adapter returns the injected legacy callable. Reading
  canonical here would serve stale data, so it does not.

Because of this, repointing a reader to the adapter while the flag is OFF is a
behavioral no-op (still legacy) — the switch to canonical happens atomically for
every repointed reader the moment the flag flips. It lives in the legacy ``core``
layer (float↔Decimal bridging allowed); the canonical context stays Decimal-only.
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
        if is_cutover_enabled(conn, env=self._env):
            return self._canonical(conn, str(product_id),
                                   None if branch_id is None else str(branch_id))
        if self._legacy_available is not None:
            return _dec(self._legacy_available(product_id, branch_id))
        # No legacy fallback available → best-effort canonical.
        return self._canonical(conn, str(product_id),
                               None if branch_id is None else str(branch_id))

    def available_float(self, product_id, branch_id=None) -> float:
        """Compat shim for legacy callers that expect a float."""
        return float(self.available(product_id, branch_id))

    # ── internals ────────────────────────────────────────────────────────────
    def _canonical(self, conn, product_id: str, branch_id: str | None) -> Decimal:
        if branch_id is not None:
            return InventoryAvailabilityQueryService(conn).get_availability(
                product_id=product_id, branch_id=branch_id).available
        # no branch → total available across branches
        rows = conn.execute(
            "SELECT quantity, reserved_quantity FROM inventory_balances"
            " WHERE product_id=? AND inventory_status='AVAILABLE'", (product_id,)).fetchall()
        total = Decimal("0")
        for r in rows:
            total += _dec(r[0]) - _dec(r[1])
        return total
