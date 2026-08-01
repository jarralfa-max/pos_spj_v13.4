"""P0-B (§6.2) — real optimistic locking on inventory_balances.

The balance projection carries a version; a stale write (a second writer that
loaded the same version) must be rejected with InventoryConcurrencyError instead
of silently overwriting (last-write-wins). A fresh insert and a normal sequential
update still succeed.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
from backend.domain.inventory.exceptions import InventoryConcurrencyError
from backend.infrastructure.db.repositories.inventory.inventory_balance_repository import (
    InventoryBalanceRepository,
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


def _fresh():
    bal = InventoryBalance.empty(
        product_id="p1", branch_id="b1", warehouse_id="w1",
        inventory_status=InventoryStatus.AVAILABLE, location_id="loc1")
    bal.apply_delta(quantity=Decimal("10"))  # version 0 → 1
    return bal


def test_fresh_insert_succeeds(conn):
    repo = InventoryBalanceRepository(conn)
    repo.upsert(_fresh())
    got = repo.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                   location_id="loc1")
    assert got.quantity == Decimal("10") and got.version == 1


def test_sequential_update_succeeds(conn):
    repo = InventoryBalanceRepository(conn)
    repo.upsert(_fresh())
    reread = repo.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                      location_id="loc1")
    reread.apply_delta(quantity=Decimal("5"))  # version 1 → 2
    repo.upsert(reread)
    got = repo.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                   location_id="loc1")
    assert got.quantity == Decimal("15") and got.version == 2


def test_stale_write_is_rejected(conn):
    repo = InventoryBalanceRepository(conn)
    repo.upsert(_fresh())
    # Two readers load the same version-1 row.
    a = repo.get(product_id="p1", branch_id="b1", warehouse_id="w1", location_id="loc1")
    b = repo.get(product_id="p1", branch_id="b1", warehouse_id="w1", location_id="loc1")
    a.apply_delta(quantity=Decimal("1"))   # → version 2
    repo.upsert(a)                          # wins, row now at version 2
    b.apply_delta(quantity=Decimal("100"))  # also → version 2 (stale)
    with pytest.raises(InventoryConcurrencyError):
        repo.upsert(b)
    # the losing write did not corrupt the balance
    got = repo.get(product_id="p1", branch_id="b1", warehouse_id="w1", location_id="loc1")
    assert got.quantity == Decimal("11") and got.version == 2
