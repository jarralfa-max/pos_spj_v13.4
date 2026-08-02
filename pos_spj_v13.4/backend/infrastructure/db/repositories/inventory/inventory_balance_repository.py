"""InventoryBalanceRepository — the ledger projection store (§14).

The balance is keyed by the full stock dimension; the repository upserts by that
UNIQUE key and reads rows back as ``InventoryBalance`` domain entities. It is
written only by the balance projection (INV-6), never by UI or other contexts.
"""

from __future__ import annotations

from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
from backend.domain.inventory.exceptions import InventoryConcurrencyError
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    now_iso,
    nz,
    to_decimal,
    zn,
)


def _to_entity(row: dict) -> InventoryBalance:
    return InventoryBalance(
        id=row["id"], product_id=row["product_id"], branch_id=row["branch_id"],
        warehouse_id=row["warehouse_id"],
        inventory_status=InventoryStatus(row["inventory_status"]),
        location_id=zn(row["location_id"]), lot_id=zn(row["lot_id"]),
        serial_id=zn(row["serial_id"]),
        quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
        reserved_quantity=to_decimal(row["reserved_quantity"]),
        reserved_weight=to_decimal(row["reserved_weight"]),
        version=int(row["version"]))


class InventoryBalanceRepository(InventoryRepositoryBase):
    def get(self, *, product_id: str, branch_id: str, warehouse_id: str,
            inventory_status: InventoryStatus = InventoryStatus.AVAILABLE,
            location_id: str | None = None, lot_id: str | None = None,
            serial_id: str | None = None) -> InventoryBalance | None:
        row = self._query_one(
            "SELECT * FROM inventory_balances WHERE product_id=? AND branch_id=?"
            " AND warehouse_id=? AND location_id=? AND lot_id=? AND serial_id=?"
            " AND inventory_status=?",
            (product_id, branch_id, warehouse_id, nz(location_id), nz(lot_id),
             nz(serial_id), enum_value(inventory_status)))
        return _to_entity(row) if row else None

    def upsert(self, balance: InventoryBalance) -> None:
        """Persist a balance with real optimistic locking (§6.2).

        The domain increments ``version`` on each in-memory mutation, so the stored
        row must still be at ``version - 1``. A brand-new row inserts cleanly; an
        existing row updates only when its stored version matches (the DO UPDATE
        ``WHERE`` guard). A version mismatch (a concurrent writer moved the row)
        leaves the row untouched (rowcount 0) and raises InventoryConcurrencyError —
        never a silent last-write-wins overwrite.
        """
        cursor = self._conn.execute(
            "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
            " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
            " reserved_quantity, reserved_weight, version, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(product_id, branch_id, warehouse_id, location_id, lot_id,"
            " serial_id, inventory_status) DO UPDATE SET"
            " quantity=excluded.quantity, weight=excluded.weight,"
            " reserved_quantity=excluded.reserved_quantity,"
            " reserved_weight=excluded.reserved_weight,"
            " version=excluded.version, updated_at=excluded.updated_at"
            " WHERE inventory_balances.version = excluded.version - 1",
            (balance.id, balance.product_id, balance.branch_id, balance.warehouse_id,
             nz(balance.location_id), nz(balance.lot_id), nz(balance.serial_id),
             enum_value(balance.inventory_status), dec_str(balance.quantity),
             dec_str(balance.weight), dec_str(balance.reserved_quantity),
             dec_str(balance.reserved_weight), balance.version, now_iso()))
        if cursor.rowcount == 0:
            raise InventoryConcurrencyError(
                "Conflicto de concurrencia optimista al actualizar el balance "
                f"(product_id={balance.product_id}, branch_id={balance.branch_id}, "
                f"warehouse_id={balance.warehouse_id}); versión esperada "
                f"{balance.version - 1}")

    def list_by_product_branch(self, product_id: str, branch_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_balances WHERE product_id=? AND branch_id=?"
            " ORDER BY warehouse_id, inventory_status", (product_id, branch_id))

    def list_by_lot(self, product_id: str, lot_id: str) -> list[dict]:
        """Every balance bucket holding stock of a specific lot (across branches,
        warehouses, locations and statuses) — used to move a lot between quality
        buckets (§9.1)."""
        return self._query(
            "SELECT * FROM inventory_balances WHERE product_id=? AND lot_id=?"
            " ORDER BY branch_id, warehouse_id, inventory_status",
            (product_id, nz(lot_id)))
