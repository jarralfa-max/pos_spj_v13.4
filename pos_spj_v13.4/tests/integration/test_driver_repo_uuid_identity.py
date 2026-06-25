"""FASE 7 (delivery) — DriverRepository mints UUIDv7 (no lastrowid/AUTOINCREMENT)."""
import sqlite3, uuid
import pytest
from repositories.driver_repository import DriverRepository


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    return DriverRepository(c)


def test_create_driver_returns_uuid(repo):
    did = repo.create_driver({"nombre": "Repa", "sucursal_id": str(uuid.uuid4())})
    assert isinstance(did, str) and uuid.UUID(did)
    assert repo.db.execute("SELECT id FROM drivers").fetchone()["id"] == did


def test_create_driver_cut_returns_uuid(repo):
    cid = repo.create_driver_cut({"driver_id": str(uuid.uuid4()), "driver_nombre": "R"})
    assert isinstance(cid, str) and uuid.UUID(cid)
