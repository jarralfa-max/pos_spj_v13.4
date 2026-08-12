"""WarehouseRepository — warehouses, zones and storage locations (§12)."""

from __future__ import annotations

from backend.domain.inventory.entities.warehouse import (
    StorageLocation,
    Warehouse,
    WarehouseZone,
)
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    enum_value,
    opt_dec_str,
)


def _b(flag: bool) -> int:
    return 1 if flag else 0


class WarehouseRepository(InventoryRepositoryBase):
    # ── warehouses ────────────────────────────────────────────────────────
    def save_warehouse(self, wh: Warehouse) -> None:
        self._execute(
            "INSERT INTO warehouses (id, code, name, branch_id, warehouse_type, status,"
            " temperature_profile, capacity, capacity_uom, allow_sales_allocation,"
            " allow_purchase_receipt, allow_production, allow_quarantine, created_at,"
            " updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " warehouse_type=excluded.warehouse_type, status=excluded.status,"
            " temperature_profile=excluded.temperature_profile,"
            " capacity=excluded.capacity, capacity_uom=excluded.capacity_uom,"
            " allow_sales_allocation=excluded.allow_sales_allocation,"
            " allow_purchase_receipt=excluded.allow_purchase_receipt,"
            " allow_production=excluded.allow_production,"
            " allow_quarantine=excluded.allow_quarantine, updated_at=excluded.updated_at",
            (wh.id, wh.code, wh.name, wh.branch_id, enum_value(wh.warehouse_type),
             enum_value(wh.status), wh.temperature_profile, opt_dec_str(wh.capacity),
             wh.capacity_uom, _b(wh.allow_sales_allocation), _b(wh.allow_purchase_receipt),
             _b(wh.allow_production), _b(wh.allow_quarantine),
             wh.created_at, wh.updated_at))

    def get_warehouse(self, warehouse_id: str) -> dict | None:
        return self._query_one("SELECT * FROM warehouses WHERE id=?", (warehouse_id,))

    def get_by_code(self, code: str) -> dict | None:
        return self._query_one("SELECT * FROM warehouses WHERE code=?", (code,))

    def list_by_branch(self, branch_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM warehouses WHERE branch_id=? ORDER BY code", (branch_id,))

    # ── zones ─────────────────────────────────────────────────────────────
    def save_zone(self, zone: WarehouseZone) -> None:
        self._execute(
            "INSERT INTO warehouse_zones (id, warehouse_id, code, name, zone_type)"
            " VALUES (?,?,?,?,?) ON CONFLICT(warehouse_id, code) DO UPDATE SET"
            " name=excluded.name, zone_type=excluded.zone_type",
            (zone.id, zone.warehouse_id, zone.code, zone.name, enum_value(zone.zone_type)))

    def list_zones(self, warehouse_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM warehouse_zones WHERE warehouse_id=? ORDER BY code",
            (warehouse_id,))

    # ── locations ─────────────────────────────────────────────────────────
    def save_location(self, loc: StorageLocation) -> None:
        self._execute(
            "INSERT INTO storage_locations (id, warehouse_id, zone_id,"
            " parent_location_id, code, name, level, status, capacity)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(warehouse_id, code) DO UPDATE SET name=excluded.name,"
            " zone_id=excluded.zone_id, parent_location_id=excluded.parent_location_id,"
            " level=excluded.level, status=excluded.status, capacity=excluded.capacity",
            (loc.id, loc.warehouse_id, loc.zone_id, loc.parent_location_id, loc.code,
             loc.name, loc.level, enum_value(loc.status), opt_dec_str(loc.capacity)))

    def get_location(self, location_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM storage_locations WHERE id=?", (location_id,))

    def get_location_by_code(self, warehouse_id: str, code: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM storage_locations WHERE warehouse_id=? AND code=?",
            (warehouse_id, code))

    def save_technical_location(self, *, location_id: str, warehouse_id: str,
                                code: str, name: str, location_type: str) -> None:
        """Persist a canonical technical location (§8) with its own UUID + type."""
        self._execute(
            "INSERT INTO storage_locations (id, warehouse_id, zone_id,"
            " parent_location_id, code, name, level, status, location_type)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(warehouse_id, code) DO UPDATE SET name=excluded.name,"
            " location_type=excluded.location_type, status=excluded.status",
            (location_id, warehouse_id, None, None, code, name, 0, "ACTIVE",
             location_type))

    def list_locations(self, warehouse_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM storage_locations WHERE warehouse_id=? ORDER BY code",
            (warehouse_id,))
