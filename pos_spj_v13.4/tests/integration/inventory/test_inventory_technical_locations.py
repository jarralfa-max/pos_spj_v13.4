"""P0-B (§8) — canonical technical locations with real UUIDs per warehouse.

Each warehouse gets one real storage location (its own UUIDv7) per technical type,
never the warehouse_id used as a location. Seeding is idempotent.
"""

import sqlite3

import pytest

from backend.application.inventory.use_cases import EnsureTechnicalLocationsUseCase
from backend.application.inventory.use_cases.ensure_technical_locations import (
    technical_code,
)
from backend.domain.inventory.enums import TechnicalLocationType
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


def test_seeds_all_eight_technical_locations_with_uuidv7(conn):
    result = EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="w1")
    assert set(result) == {t.value for t in TechnicalLocationType}
    assert len(result) == 8
    for loc_id in result.values():
        assert is_uuidv7(loc_id)  # real UUIDv7, not warehouse_id


def test_locations_are_persisted_with_type(conn):
    EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="w1")
    rows = conn.execute(
        "SELECT code, location_type FROM storage_locations WHERE warehouse_id='w1'"
        " ORDER BY code").fetchall()
    assert len(rows) == 8
    types = {r["location_type"] for r in rows}
    assert types == {t.value for t in TechnicalLocationType}
    quarantine = conn.execute(
        "SELECT id FROM storage_locations WHERE warehouse_id='w1' AND code=?",
        (technical_code(TechnicalLocationType.QUARANTINE),)).fetchone()
    assert quarantine is not None


def test_idempotent_re_run_does_not_duplicate(conn):
    first = EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="w1")
    second = EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="w1")
    assert first == second  # same ids returned
    count = conn.execute(
        "SELECT COUNT(*) FROM storage_locations WHERE warehouse_id='w1'").fetchone()[0]
    assert count == 8


def test_locations_are_per_warehouse(conn):
    a = EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="w1")
    b = EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="w2")
    # distinct warehouses get distinct location ids for the same type
    assert a["AVAILABLE"] != b["AVAILABLE"]
    total = conn.execute("SELECT COUNT(*) FROM storage_locations").fetchone()[0]
    assert total == 16


def test_requires_warehouse_id(conn):
    with pytest.raises(ValueError):
        EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id="")
