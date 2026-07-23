"""INV-27 corte — InventoryApplicationService sobre el repositorio canónico.

Con CanonicalInventoryRepository inyectado (como en app_container), las
mutaciones increase/decrease/adjust/transfer postean al ledger canónico
(inventory_balances/inventory_ledger), no a inventory_stock legacy, preservando
el contrato InventoryMutationResult.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.services.canonical_inventory_repository import (
    CanonicalInventoryRepository,
)
from backend.application.services.inventory_application_service import (
    InventoryApplicationService,
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


def _svc(conn):
    return InventoryApplicationService(repository=CanonicalInventoryRepository(conn))


def _avail(conn, product_id="p1", branch_id="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def test_increase_posts_to_canonical_ledger(conn):
    r = _svc(conn).increase_stock(
        "p1", "b1", 10.0, "kg", "compra", "op-inc-1", "purchase","PURCHASE",None,"u1")
    assert r.success and r.stock_after == 10.0
    assert _avail(conn) == Decimal("10")
    assert conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 1


def test_decrease_and_negative_block(conn):
    svc = _svc(conn)
    svc.increase_stock("p1", "b1", 10.0, "kg", "seed", "op-seed", "inv","INV",None,"u1")
    r = svc.decrease_stock("p1", "b1", 4.0, "kg", "consumo", "op-dec-1", "inv","INV",None,"u1")
    assert r.success and _avail(conn) == Decimal("6")
    blocked = svc.decrease_stock("p1", "b1", 99.0, "kg", "x", "op-dec-2", "inv","INV",None,"u1")
    assert not blocked.success
    assert _avail(conn) == Decimal("6")


def test_increase_is_idempotent(conn):
    svc = _svc(conn)
    svc.increase_stock("p1", "b1", 10.0, "kg", "c", "op-inc-1", "inv","INV",None,"u1")
    svc.increase_stock("p1", "b1", 10.0, "kg", "c", "op-inc-1", "inv","INV",None,"u1")  # replay
    assert _avail(conn) == Decimal("10")  # once


def test_adjust_sets_target_quantity(conn):
    svc = _svc(conn)
    svc.increase_stock("p1", "b1", 10.0, "kg", "seed", "op-seed", "inv","INV",None,"u1")
    r = svc.adjust_stock("p1", "b1", new_quantity=7.0, unit="kg",
                         reason="conteo", operation_id="op-adj-1",
                         source_module="inv", user_name="u1")
    assert r.success
    assert _avail(conn) == Decimal("7")  # 10 → 7 (ADJUST_DECREASE of 3)


def test_transfer_moves_between_branches(conn):
    svc = _svc(conn)
    svc.increase_stock("p1", "b1", 10.0, "kg", "seed", "op-seed", "inv","INV",None,"u1")
    r = svc.transfer_stock("p1", "b1", "b2", 3.0, "kg", "traslado", "op-tr-1", "inv", "T", None, "u1")
    assert r.success
    assert _avail(conn, branch_id="b1") == Decimal("7")
    assert _avail(conn, branch_id="b2") == Decimal("3")
