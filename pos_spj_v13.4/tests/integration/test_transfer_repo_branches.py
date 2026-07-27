"""FASE 7 (transferencias) — branch list lives in the repo, not the UI."""
import sqlite3
import pytest
from repositories.transferencias import TransferRepository


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        "CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1);"
        "INSERT INTO sucursales VALUES ('b1','Centro',1),('b2','Norte',1),('b3','Cerrada',0);"
    )
    c.commit()
    return c


def test_list_active_branches_returns_active_ordered(db):
    rows = TransferRepository(db).list_active_branches()
    assert [r["nombre"] for r in rows] == ["Centro", "Norte"]  # active only, ordered
    assert all(isinstance(r["id"], str) for r in rows)         # UUID-ready ids
