"""INV-5 — warehouses/zones/locations: CRUD, states, hierarchy, permissions (§12)."""

import sqlite3
from decimal import Decimal

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import WarehouseQueryService
from backend.application.inventory.use_cases import (
    CreateLocationUseCase,
    CreateWarehouseUseCase,
    CreateZoneUseCase,
    DeactivateLocationUseCase,
    DeactivateWarehouseUseCase,
    SetLocationStatusUseCase,
    SetWarehouseStatusUseCase,
    UpdateLocationUseCase,
    UpdateWarehouseUseCase,
)
from backend.domain.inventory.enums import (
    TechnicalLocationType,
    WarehouseType,
    WarehouseZoneType,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _warehouse(conn, code="WH1"):
    return CreateWarehouseUseCase().execute(
        conn, code=code, name="Central", branch_id="b1",
        warehouse_type=WarehouseType.CENTRAL, actor_user_id="mgr")


class TestWarehouse:
    def test_create_and_list(self, conn):
        r = _warehouse(conn)
        assert r.success
        rows = WarehouseQueryService(conn).list_warehouses(branch_id="b1")
        assert len(rows) == 1 and rows[0]["code"] == "WH1"

    def test_create_is_idempotent_by_code(self, conn):
        _warehouse(conn)
        r = _warehouse(conn)
        assert r.success and r.data.get("idempotent") is True
        assert len(WarehouseQueryService(conn).list_warehouses(branch_id="b1")) == 1

    def test_block_and_activate(self, conn):
        wid = _warehouse(conn).entity_id
        SetWarehouseStatusUseCase().execute(conn, warehouse_id=wid, activate=False,
                                            actor_user_id="mgr", reason="mantenimiento")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.warehouses.get_warehouse(wid)["status"] == "BLOCKED"
        SetWarehouseStatusUseCase().execute(conn, warehouse_id=wid, activate=True,
                                            actor_user_id="mgr")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.warehouses.get_warehouse(wid)["status"] == "ACTIVE"

    def test_create_requires_permission(self, conn):
        class Denies:
            def has_permission(self, u, p):
                return False
        r = CreateWarehouseUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, code="WH9", name="x", branch_id="b1",
            warehouse_type=WarehouseType.STORE, actor_user_id="clerk")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_create_provisions_technical_locations(self, conn):
        """§20: un almacén creado manualmente (no sólo el de aprovisionamiento
        por defecto) recibe sus ubicaciones técnicas."""
        wid = _warehouse(conn).entity_id
        locations = WarehouseQueryService(conn).list_locations(warehouse_id=wid)
        codes = {loc["code"] for loc in locations}
        assert len(locations) == len(TechnicalLocationType)
        for loc_type in TechnicalLocationType:
            assert f"TECH:{loc_type.value}" in codes

    def test_create_persists_capacity_and_temperature_profile(self, conn):
        r = CreateWarehouseUseCase().execute(
            conn, code="WH-COLD", name="Frío", branch_id="b1",
            warehouse_type=WarehouseType.COLD_STORAGE, actor_user_id="mgr",
            temperature_profile="REFRIGERADO 0-4C", capacity=Decimal("120.5"),
            capacity_uom="m3")
        with InventoryUnitOfWork(conn) as uow:
            row = uow.warehouses.get_warehouse(r.entity_id)
        assert row["temperature_profile"] == "REFRIGERADO 0-4C"
        assert row["capacity"] == "120.5"
        assert row["capacity_uom"] == "m3"

    def test_update_warehouse_edits_mutable_fields(self, conn):
        wid = _warehouse(conn).entity_id
        r = UpdateWarehouseUseCase().execute(
            conn, warehouse_id=wid, actor_user_id="mgr", name="Central renombrado",
            temperature_profile="AMBIENTE", capacity=Decimal("50"), capacity_uom="tarimas")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            row = uow.warehouses.get_warehouse(wid)
        assert row["name"] == "Central renombrado"
        assert row["temperature_profile"] == "AMBIENTE"
        assert row["capacity"] == "50"
        assert row["capacity_uom"] == "tarimas"

    def test_update_warehouse_requires_permission(self, conn):
        wid = _warehouse(conn).entity_id

        class Denies:
            def has_permission(self, u, p):
                return False
        r = UpdateWarehouseUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, warehouse_id=wid, actor_user_id="clerk", name="x")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_deactivate_warehouse(self, conn):
        wid = _warehouse(conn).entity_id
        r = DeactivateWarehouseUseCase().execute(
            conn, warehouse_id=wid, actor_user_id="mgr", reason="cierre definitivo")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.warehouses.get_warehouse(wid)["status"] == "INACTIVE"

    def test_deactivate_warehouse_requires_its_own_permission(self, conn):
        wid = _warehouse(conn).entity_id

        class OnlyBlock:
            def has_permission(self, u, p):
                from backend.application.inventory.permissions import (
                    InventoryPermissions,
                )
                return p == InventoryPermissions.WAREHOUSE_BLOCK
        r = DeactivateWarehouseUseCase(InventoryAuthorizationPolicy(OnlyBlock())).execute(
            conn, warehouse_id=wid, actor_user_id="mgr")
        assert not r.success and r.error_code == "PERMISSION_DENIED"


class TestZonesAndLocations:
    def test_zone_and_location_hierarchy(self, conn):
        wid = _warehouse(conn).entity_id
        CreateZoneUseCase().execute(conn, warehouse_id=wid, code="Z1", name="Recibo",
                                    zone_type=WarehouseZoneType.RECEIVING, actor_user_id="mgr")
        aisle = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1", name="Pasillo 1", actor_user_id="mgr",
            level=0).entity_id
        rack = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="A1-R1", name="Rack 1", actor_user_id="mgr",
            parent_location_id=aisle, level=1).entity_id
        assert rack

        svc = WarehouseQueryService(conn)
        assert len(svc.list_zones(warehouse_id=wid)) == 1
        # §20: CreateWarehouseUseCase auto-provisiona las ubicaciones técnicas
        # (TECH:*), así que el árbol trae esas raíces además de la manual "A1".
        tree = svc.location_hierarchy(warehouse_id=wid)
        by_code = {node.code: node for node in tree}
        assert "A1" in by_code
        assert len(by_code["A1"].children) == 1
        assert by_code["A1"].children[0].code == "A1-R1"
        assert any(code.startswith("TECH:") for code in by_code)

    def test_location_rejects_unknown_parent(self, conn):
        wid = _warehouse(conn).entity_id
        r = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="X", name="x", actor_user_id="mgr",
            parent_location_id="nope")
        assert not r.success and r.error_code == "NOT_FOUND"

    def test_block_location(self, conn):
        wid = _warehouse(conn).entity_id
        loc = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="L1", name="Pos 1", actor_user_id="mgr").entity_id
        SetLocationStatusUseCase().execute(conn, location_id=loc, activate=False,
                                           actor_user_id="mgr")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.warehouses.get_location(loc)["status"] == "BLOCKED"

    def test_location_manage_requires_permission(self, conn):
        wid = _warehouse(conn).entity_id

        class Denies:
            def has_permission(self, u, p):
                return False
        r = CreateLocationUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, warehouse_id=wid, code="L2", name="x", actor_user_id="clerk")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_location_persists_capacity(self, conn):
        wid = _warehouse(conn).entity_id
        r = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="L3", name="Pos 3", actor_user_id="mgr",
            capacity=Decimal("12.750"))
        with InventoryUnitOfWork(conn) as uow:
            row = uow.warehouses.get_location(r.entity_id)
        assert row["capacity"] == "12.750"

    def test_update_location_edits_name_and_capacity(self, conn):
        wid = _warehouse(conn).entity_id
        loc = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="L4", name="Pos 4", actor_user_id="mgr").entity_id
        r = UpdateLocationUseCase().execute(
            conn, location_id=loc, actor_user_id="mgr", name="Pos 4 renombrada",
            capacity=Decimal("8"))
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            row = uow.warehouses.get_location(loc)
        assert row["name"] == "Pos 4 renombrada"
        assert row["capacity"] == "8"

    def test_deactivate_location(self, conn):
        wid = _warehouse(conn).entity_id
        loc = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="L5", name="Pos 5", actor_user_id="mgr").entity_id
        r = DeactivateLocationUseCase().execute(
            conn, location_id=loc, actor_user_id="mgr", reason="fuera de uso")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.warehouses.get_location(loc)["status"] == "INACTIVE"

    def test_deactivate_location_requires_permission(self, conn):
        wid = _warehouse(conn).entity_id
        loc = CreateLocationUseCase().execute(
            conn, warehouse_id=wid, code="L6", name="Pos 6", actor_user_id="mgr").entity_id

        class Denies:
            def has_permission(self, u, p):
                return False
        r = DeactivateLocationUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, location_id=loc, actor_user_id="clerk")
        assert not r.success and r.error_code == "PERMISSION_DENIED"
