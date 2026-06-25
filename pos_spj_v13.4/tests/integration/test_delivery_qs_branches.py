"""FASE 7 (delivery) — branch list comes from the QueryService, not UI SQL."""
import sqlite3
import pytest
from core.delivery.application.query_service import DeliveryQueryService


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT);"
        "INSERT INTO sucursales VALUES ('b2','Norte'),('b1','Centro');"
    )
    c.commit()
    return c


def test_list_active_branches_ordered_tuples(db):
    out = DeliveryQueryService(db).list_active_branches()
    assert out == [("b1", "Centro"), ("b2", "Norte")]  # ordered by nombre, str ids
