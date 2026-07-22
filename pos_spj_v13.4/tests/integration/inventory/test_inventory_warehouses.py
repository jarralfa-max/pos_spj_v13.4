"""INV-5 — warehouses/zones/locations: CRUD, states, hierarchy, permissions (§12)."""

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import WarehouseQueryService
from backend.application.inventory.use_cases import (
    CreateLocationUseCase,
    CreateWarehouseUseCase,
    CreateZoneUseCase,
    SetLocationStatusUseCase,
    SetWarehouseStatusUseCase,
)
from backend.domain.inventory.enums import (
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
        tree = svc.location_hierarchy(warehouse_id=wid)
        assert len(tree) == 1 and tree[0].code == "A1"
        assert len(tree[0].children) == 1 and tree[0].children[0].code == "A1-R1"

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
