"""InventoryReconciliationService — canonical vs legacy stock parity (INV-27).

Before flipping the cutover flag, operators must prove the canonical projection
matches the legacy stock it will replace. This read-only service compares
available quantity per (product, branch) between ``inventory_balances`` (canonical)
and the legacy stock table, reporting any drift. Decimal throughout; if the legacy
table is absent it reports canonical-only rows rather than failing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)

# Legacy stock tables in priority order (first that exists is used).
_LEGACY_STOCK = (
    ("inventario_actual", "producto_id", "sucursal_id", "cantidad"),
    ("inventory_stock", "product_id", "branch_id", "quantity"),
)


@dataclass(frozen=True, slots=True)
class ReconciliationRow:
    product_id: str
    branch_id: str
    canonical: Decimal
    legacy: Decimal

    @property
    def drift(self) -> Decimal:
        return self.canonical - self.legacy

    @property
    def in_sync(self) -> bool:
        return self.drift == 0


class InventoryReconciliationService(InventoryRepositoryBase):
    def _table_exists(self, name: str) -> bool:
        return self._query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)) is not None

    def _legacy_source(self):
        for table, prod, branch, qty in _LEGACY_STOCK:
            if self._table_exists(table):
                return table, prod, branch, qty
        return None

    def _canonical_available(self) -> dict[tuple[str, str], Decimal]:
        rows = self._query(
            "SELECT product_id, branch_id, quantity, reserved_quantity"
            " FROM inventory_balances WHERE inventory_status=?",
            (InventoryStatus.AVAILABLE.value,))
        out: dict[tuple[str, str], Decimal] = {}
        for r in rows:
            key = (str(r["product_id"]), str(r["branch_id"]))
            out[key] = out.get(key, Decimal("0")) + (
                to_decimal(r["quantity"]) - to_decimal(r["reserved_quantity"]))
        return out

    def _legacy_stock(self) -> dict[tuple[str, str], Decimal]:
        source = self._legacy_source()
        if source is None:
            return {}
        table, prod, branch, qty = source
        rows = self._query(
            f"SELECT {prod} AS p, {branch} AS b, {qty} AS q FROM {table}")
        out: dict[tuple[str, str], Decimal] = {}
        for r in rows:
            key = (str(r["p"]), str(r["b"]))
            out[key] = out.get(key, Decimal("0")) + to_decimal(r["q"])
        return out

    def reconcile(self) -> list[ReconciliationRow]:
        canonical = self._canonical_available()
        legacy = self._legacy_stock()
        rows = []
        for key in sorted(set(canonical) | set(legacy)):
            rows.append(ReconciliationRow(
                product_id=key[0], branch_id=key[1],
                canonical=canonical.get(key, Decimal("0")),
                legacy=legacy.get(key, Decimal("0"))))
        return rows

    def drifts(self) -> list[ReconciliationRow]:
        return [r for r in self.reconcile() if not r.in_sync]

    def is_in_sync(self) -> bool:
        """True only when a legacy source exists and every row matches."""
        return self._legacy_source() is not None and not self.drifts()
