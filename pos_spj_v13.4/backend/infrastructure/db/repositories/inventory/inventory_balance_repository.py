"""InventoryBalanceRepository — the ledger projection store (§14).

The balance is keyed by the full stock dimension; the repository upserts by that
UNIQUE key and reads rows back as ``InventoryBalance`` domain entities. It is
written only by the balance projection (INV-6), never by UI or other contexts.
"""

from __future__ import annotations

from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
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
        self._execute(
            "INSERT INTO inventory_balances (id, product_id, branch_id, warehouse_id,"
            " location_id, lot_id, serial_id, inventory_status, quantity, weight,"
            " reserved_quantity, reserved_weight, version, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(product_id, branch_id, warehouse_id, location_id, lot_id,"
            " serial_id, inventory_status) DO UPDATE SET"
            " quantity=excluded.quantity, weight=excluded.weight,"
            " reserved_quantity=excluded.reserved_quantity,"
            " reserved_weight=excluded.reserved_weight,"
            " version=excluded.version, updated_at=excluded.updated_at",
            (balance.id, balance.product_id, balance.branch_id, balance.warehouse_id,
             nz(balance.location_id), nz(balance.lot_id), nz(balance.serial_id),
             enum_value(balance.inventory_status), dec_str(balance.quantity),
             dec_str(balance.weight), dec_str(balance.reserved_quantity),
             dec_str(balance.reserved_weight), balance.version, now_iso()))

    def list_by_product_branch(self, product_id: str, branch_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_balances WHERE product_id=? AND branch_id=?"
            " ORDER BY warehouse_id, inventory_status", (product_id, branch_id))
