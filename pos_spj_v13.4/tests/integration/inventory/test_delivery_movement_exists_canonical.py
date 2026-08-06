"""P2 repoint — delivery adapter's idempotency check reads the canonical ledger.

``ReservationServiceInventoryAdapter.commit_for_order`` posts stock deductions
through ``InventoryService.deduct_stock`` — a canonical shim (INV-27) that has not
written the legacy ``movimientos_inventario`` table in a long time. Its
``_movement_exists`` pre-check queried that legacy table anyway, so it always
returned False (stale, dead check) regardless of whether the item was already
committed. It now queries the canonical ``inventory_ledger`` — the table the
deduction actually lands in — restoring the intended idempotency-skip behavior.
"""

import sqlite3

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.delivery.infrastructure.inventory_reservation_adapter import (
    ReservationServiceInventoryAdapter,
)
from core.services.inventory_service import InventoryService


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    return c


def test_movement_exists_true_after_canonical_deduct_stock():
    conn = _conn()
    InventoryService(conn).add_stock(
        product_id="p1", branch_id="b1", qty=10, unit_cost=5,
        reference_type="seed", reference_id="seed-1", operation_id="seed-op",
        user="u1")
    InventoryService(conn).deduct_stock(
        product_id="p1", branch_id="b1", qty=3,
        reference_type="delivery_prepared", reference_id="order-1",
        operation_id="delivery:order-1:item:p1:commit", user="sistema")
    adapter = ReservationServiceInventoryAdapter(conn)
    assert adapter._movement_exists("delivery:order-1:item:p1:commit") is True


def test_movement_exists_false_for_unposted_operation():
    conn = _conn()
    adapter = ReservationServiceInventoryAdapter(conn)
    assert adapter._movement_exists("delivery:order-9:item:p9:commit") is False


def test_movement_exists_scoped_to_the_exact_operation_id():
    conn = _conn()
    InventoryService(conn).add_stock(
        product_id="p1", branch_id="b1", qty=10, unit_cost=5,
        reference_type="seed", reference_id="seed-1", operation_id="seed-op",
        user="u1")
    InventoryService(conn).deduct_stock(
        product_id="p1", branch_id="b1", qty=3,
        reference_type="delivery_prepared", reference_id="order-1",
        operation_id="delivery:order-1:item:p1:commit", user="sistema")
    adapter = ReservationServiceInventoryAdapter(conn)
    # a different item's operation_id was never posted → not idempotent-skipped
    assert adapter._movement_exists("delivery:order-1:item:p2:commit") is False
