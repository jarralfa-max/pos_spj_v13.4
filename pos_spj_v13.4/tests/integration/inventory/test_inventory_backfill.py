"""INV-27 repoint step 1 — legacy stock backfill into the canonical ledger."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from migrations.deferred import backfill_legacy_stock


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _legacy_actual(conn, rows):
    conn.execute("CREATE TABLE inventario_actual (id TEXT, producto_id TEXT,"
                 " sucursal_id TEXT, cantidad REAL)")
    conn.executemany("INSERT INTO inventario_actual VALUES (?,?,?,?)",
                     [(f"{p}-{b}", p, b, q) for p, b, q in rows])
    conn.commit()


def _avail(conn, product, branch):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product, branch_id=branch).available


class TestBackfill:
    def test_refuses_without_env_guard(self, conn):
        _legacy_actual(conn, [("p1", "b1", 10.0)])
        with pytest.raises(RuntimeError):
            backfill_legacy_stock.run(conn, env={})

    def test_seeds_canonical_balances_from_legacy(self, conn):
        _legacy_actual(conn, [("p1", "b1", 10.0), ("p2", "b1", 3.5)])
        result = backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
        assert result["source"] == "inventario_actual" and result["seeded"] == 2
        assert _avail(conn, "p1", "b1") == Decimal("10.000000")
        assert _avail(conn, "p2", "b1") == Decimal("3.500000")
        # ledger-first: a real movement backs the balance
        mt = conn.execute("SELECT movement_type FROM inventory_ledger"
                          " WHERE source_document_type='LEGACY_BACKFILL' LIMIT 1").fetchone()
        assert mt["movement_type"] == "ADJUSTMENT_IN"

    def test_is_idempotent(self, conn):
        _legacy_actual(conn, [("p1", "b1", 10.0)])
        backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
        r2 = backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
        assert r2["seeded"] == 0  # replay dedup by operation_id
        assert _avail(conn, "p1", "b1") == Decimal("10.000000")  # not doubled

    def test_skips_zero_and_negative(self, conn):
        _legacy_actual(conn, [("p1", "b1", 0.0), ("p2", "b1", -5.0), ("p3", "b1", 4.0)])
        result = backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
        assert result["seeded"] == 1 and result["skipped"] == 2

    def test_falls_back_to_inventory_stock(self, conn):
        conn.execute("CREATE TABLE inventory_stock (product_id TEXT, branch_id TEXT,"
                     " quantity REAL, unit TEXT)")
        conn.execute("INSERT INTO inventory_stock VALUES ('p9','b2',7.0,'unit')")
        conn.commit()
        result = backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
        assert result["source"] == "inventory_stock" and result["seeded"] == 1
        assert _avail(conn, "p9", "b2") == Decimal("7.000000")

    def test_no_legacy_table_is_noop(self, conn):
        result = backfill_legacy_stock.run(conn, env={"INVENTORY_ALLOW_BACKFILL": "1"})
        assert result["source"] is None and result["seeded"] == 0

    def test_not_registered_in_engine(self):
        from migrations.engine import MIGRATIONS
        assert "migrations.deferred.backfill_legacy_stock" not in {m.module for m in MIGRATIONS}
