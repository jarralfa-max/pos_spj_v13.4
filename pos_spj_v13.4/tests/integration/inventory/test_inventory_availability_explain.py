"""P0-C (§9.3) — availability query explains a shortage across every bucket.

Stock can exist yet not be available to promise (reserved, quarantined,
quality-blocked, damaged, expired, allocated, in-transit…). The availability
query breaks the on-hand down per physical bucket so a caller can explain WHY a
product is short, not just report a number.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
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


def _put(conn, status, qty, *, reserved="0", loc="loc1"):
    bal = InventoryBalance.empty(
        product_id="p1", branch_id="b1", warehouse_id="w1",
        inventory_status=status, location_id=loc)
    bal.apply_delta(quantity=Decimal(qty))
    if reserved != "0":
        bal.reserve(quantity=Decimal(reserved))
    with InventoryUnitOfWork(conn) as uow:
        uow.balances.upsert(bal)


def _explain(conn):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id="p1", branch_id="b1")


def test_available_is_on_hand_minus_reserved(conn):
    _put(conn, InventoryStatus.AVAILABLE, "10", reserved="3")
    dto = _explain(conn)
    assert dto.on_hand == Decimal("10")
    assert dto.reserved == Decimal("3")
    assert dto.available == Decimal("7")


def test_every_bucket_is_broken_out(conn):
    _put(conn, InventoryStatus.AVAILABLE, "10", loc="a")
    _put(conn, InventoryStatus.QUARANTINED, "4", loc="b")
    _put(conn, InventoryStatus.QUALITY_BLOCKED, "3", loc="c")
    _put(conn, InventoryStatus.DAMAGED, "2", loc="d")
    _put(conn, InventoryStatus.EXPIRED, "1", loc="e")
    _put(conn, InventoryStatus.ALLOCATED, "5", loc="f")
    _put(conn, InventoryStatus.IN_TRANSIT, "6", loc="g")
    dto = _explain(conn)
    assert dto.available == Decimal("10")
    assert dto.quarantined == Decimal("4")
    assert dto.blocked == Decimal("3")
    assert dto.damaged == Decimal("2")
    assert dto.expired == Decimal("1")
    assert dto.allocated == Decimal("5")
    assert dto.in_transit == Decimal("6")


def test_total_on_hand_sums_all_physical_buckets(conn):
    _put(conn, InventoryStatus.AVAILABLE, "10", loc="a")
    _put(conn, InventoryStatus.QUARANTINED, "4", loc="b")
    _put(conn, InventoryStatus.DAMAGED, "2", loc="c")
    dto = _explain(conn)
    # DISPOSED no cuenta como on-hand; los demás sí
    assert dto.total_on_hand == Decimal("16")


def test_disposed_is_not_on_hand(conn):
    _put(conn, InventoryStatus.AVAILABLE, "5", loc="a")
    _put(conn, InventoryStatus.DISPOSED, "9", loc="b")
    dto = _explain(conn)
    assert dto.total_on_hand == Decimal("5")
    assert dto.available == Decimal("5")


def test_explain_dict_accounts_for_the_shortage(conn):
    # nada disponible aunque hay stock físico: todo bloqueado/en cuarentena
    _put(conn, InventoryStatus.QUARANTINED, "8", loc="a")
    _put(conn, InventoryStatus.QUALITY_BLOCKED, "2", loc="b")
    dto = _explain(conn)
    exp = dto.explain()
    assert exp["available"] == Decimal("0")
    assert exp["total_on_hand"] == Decimal("10")
    assert exp["quarantined"] == Decimal("8")
    assert exp["blocked"] == Decimal("2")
