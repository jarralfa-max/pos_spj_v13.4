"""INV-27 — migration 134 activates the canonical cutover (backfill → flag ON)."""

from decimal import Decimal

import importlib
import sqlite3

import pytest

from backend.application.inventory.cutover import is_cutover_enabled
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

m134 = importlib.import_module(
    "migrations.standalone.134_inventory_canonical_cutover")


@pytest.fixture(autouse=True)
def _no_env_flag(monkeypatch):
    monkeypatch.delenv("INVENTORY_CANONICAL_CUTOVER", raising=False)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def test_fresh_db_sets_flag_and_is_noop_backfill(conn):
    # no legacy stock table → backfill no-op, flag still turns ON
    assert is_cutover_enabled(conn, env={}) is False
    m134.run(conn)
    assert is_cutover_enabled(conn, env={}) is True


def test_backfills_legacy_stock_and_activates(conn):
    conn.execute("CREATE TABLE inventory_stock (product_id TEXT, branch_id TEXT,"
                 " quantity REAL, unit TEXT)")
    conn.execute("INSERT INTO inventory_stock VALUES ('p1','b1',12.0,'u')")
    conn.commit()
    m134.run(conn)
    # canonical ledger now seeded from legacy, and flag ON
    assert is_cutover_enabled(conn, env={}) is True
    avail = InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1").available
    assert avail == Decimal("12")


def test_idempotent_rerun(conn):
    conn.execute("CREATE TABLE inventory_stock (product_id TEXT, branch_id TEXT,"
                 " quantity REAL, unit TEXT)")
    conn.execute("INSERT INTO inventory_stock VALUES ('p1','b1',12.0,'u')")
    conn.commit()
    m134.run(conn)
    m134.run(conn)  # re-run must not double-seed
    avail = InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1").available
    assert avail == Decimal("12")
