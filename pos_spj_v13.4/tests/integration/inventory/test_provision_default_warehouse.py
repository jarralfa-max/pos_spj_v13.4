"""P0-E prerequisite — a real default warehouse per branch (§8, §12).

CLAUDE.md forbids warehouse_id=branch_id, but the Sales/Production/Purchase
bridges rely on that substitution today because no branch has ever had a real
warehouse (no migration/seed creates one, and the Almacenes UI has no create
action yet). ProvisionDefaultWarehouseUseCase is the prerequisite that must
run before those bridges can be safely repointed: idempotently ensure a
branch has one CENTRAL warehouse, with all allocation flags on and its
technical locations seeded.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.inventory.composition import InventoryUseCaseFactory
from backend.application.inventory.use_cases import (
    CreateWarehouseUseCase,
    ProvisionDefaultWarehouseUseCase,
)
from backend.application.inventory.use_cases.provision_default_warehouse import (
    default_warehouse_code,
)
from backend.domain.inventory.enums import TechnicalLocationType, WarehouseType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import is_uuidv7


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def test_creates_a_real_warehouse_distinct_from_branch_id(conn):
    result = ProvisionDefaultWarehouseUseCase().execute(
        conn, branch_id="b1", branch_name="Centro", actor_user_id="u1")
    assert result.success, result.message
    assert result.entity_id != "b1"
    assert is_uuidv7(result.entity_id)
    row = conn.execute(
        "SELECT branch_id, warehouse_type, allow_sales_allocation,"
        " allow_purchase_receipt, allow_production, allow_quarantine"
        " FROM warehouses WHERE id=?", (result.entity_id,)).fetchone()
    assert row["branch_id"] == "b1"
    assert row["warehouse_type"] == WarehouseType.CENTRAL.value
    assert (row["allow_sales_allocation"] and row["allow_purchase_receipt"]
            and row["allow_production"] and row["allow_quarantine"])


def test_seeds_technical_locations_for_the_new_warehouse(conn):
    result = ProvisionDefaultWarehouseUseCase().execute(
        conn, branch_id="b1", actor_user_id="u1")
    locations = result.data["locations"]
    assert set(locations) == {t.value for t in TechnicalLocationType}
    for loc_id in locations.values():
        assert is_uuidv7(loc_id)
        assert loc_id != result.entity_id  # ubicación real, no el almacén


def test_idempotent_second_call_reuses_the_same_warehouse(conn):
    first = ProvisionDefaultWarehouseUseCase().execute(
        conn, branch_id="b1", actor_user_id="u1")
    second = ProvisionDefaultWarehouseUseCase().execute(
        conn, branch_id="b1", actor_user_id="u1")
    assert first.entity_id == second.entity_id
    assert second.data["already_existed"] is True
    count = conn.execute(
        "SELECT COUNT(*) FROM warehouses WHERE branch_id='b1'").fetchone()[0]
    assert count == 1


def test_distinct_branches_get_distinct_warehouses(conn):
    a = ProvisionDefaultWarehouseUseCase().execute(conn, branch_id="b1", actor_user_id="u1")
    b = ProvisionDefaultWarehouseUseCase().execute(conn, branch_id="b2", actor_user_id="u1")
    assert a.entity_id != b.entity_id
    assert default_warehouse_code("b1") != default_warehouse_code("b2")


def test_requires_branch_id(conn):
    result = ProvisionDefaultWarehouseUseCase().execute(
        conn, branch_id="", actor_user_id="u1")
    assert not result.success
    assert result.error_code == "BRANCH_REQUIRED"


def test_does_not_duplicate_if_warehouse_already_created_manually(conn):
    """If someone already created a warehouse for the branch via the normal
    CreateWarehouseUseCase with the deterministic default code, provisioning
    again must recognize it (idempotent by code) instead of duplicating."""
    code = default_warehouse_code("b1")
    manual = CreateWarehouseUseCase().execute(
        conn, code=code, name="Manual", branch_id="b1",
        warehouse_type=WarehouseType.CENTRAL, actor_user_id="u1")
    assert manual.success
    result = ProvisionDefaultWarehouseUseCase().execute(
        conn, branch_id="b1", actor_user_id="u1")
    assert result.entity_id == manual.entity_id
    count = conn.execute(
        "SELECT COUNT(*) FROM warehouses WHERE branch_id='b1'").fetchone()[0]
    assert count == 1


def test_factory_builds_it_with_the_real_checker():
    factory = InventoryUseCaseFactory.for_tests()
    uc = factory.provision_default_warehouse()
    assert isinstance(uc, ProvisionDefaultWarehouseUseCase)


def test_factory_builds_create_warehouse():
    factory = InventoryUseCaseFactory.for_tests()
    uc = factory.create_warehouse()
    assert isinstance(uc, CreateWarehouseUseCase)
