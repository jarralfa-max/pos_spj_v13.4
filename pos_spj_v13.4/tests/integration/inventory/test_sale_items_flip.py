"""INV-27 FLIP (ventas) — the live SALE_ITEMS_PROCESS deduction switches from the
legacy inventory engine to a canonical SALE_ISSUE movement on the ledger.

``_wire_sale_handlers`` selects exactly ONE deduction handler by the cutover flag
(no double counting). With the flag ON the canonical bridge:
  - deducts stock from the ledger inside the sale's transaction (no premature
    commit — the outer sale owns the boundary),
  - is idempotent by operation_id,
  - aborts the sale (raises) if stock is insufficient, rolling back cleanly.
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.repositories.inventory.support_repositories import (
    InventorySettingsRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from core.events.domain_events import SALE_ITEMS_PROCESS


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


class _FakeBus:
    def __init__(self):
        self.subs: dict[str, list] = {}
        self.labels: dict[str, list] = {}

    def subscribe(self, event_type, handler, priority=0, label=""):
        self.subs.setdefault(event_type, []).append(handler)
        self.labels.setdefault(event_type, []).append(label)

    def publish(self, event_type, payload):
        for h in list(self.subs.get(event_type, [])):
            h(dict(payload))

    def handler_count(self, event_type):
        return len(self.subs.get(event_type, []))


class _Container:
    def __init__(self, db, inventory_service=None, finance_service=None):
        self.db = db
        self.inventory_service = inventory_service
        self.finance_service = finance_service


def _enable_cutover(conn):
    InventorySettingsRepository(conn).set(
        setting_key="canonical_cutover_enabled", setting_value="true")
    conn.commit()


def _seed(conn, product_id="p1", branch_id="b1", qty="10"):
    # Opening balance at location = branch_id (the POS-sellable convention the
    # backfill and the bridge both use).
    line = InventoryMovementLine.create(
        product_id=product_id, quantity=Decimal(qty), to_location_id=branch_id,
        reason_code="OPENING")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id=branch_id,
        warehouse_id=branch_id, source_module="test", source_document_type="SEED",
        source_document_id="seed", operation_id=f"seed:{product_id}:{branch_id}",
        created_by_user_id="system", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="system")


def _available(conn, product_id="p1", branch_id="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _wire(bus, container):
    from core.events.wiring import _wire_sale_handlers
    _wire_sale_handlers(bus, container)


class TestFlagSelectsHandler:
    def test_wires_canonical_bridge(self, conn):
        # corte INV-27: el wiring es canónico incondicional (motor legacy eliminado)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        _seed(conn, qty="10")
        bus.publish(SALE_ITEMS_PROCESS, {
            "branch_id": "b1", "operation_id": "s1", "sale_id": "S1",
            "items": [{"product_id": "p1", "qty": "4", "es_compuesto": 0}]})
        assert _available(conn) == Decimal("6")  # canonical ledger deducted
        row = conn.execute(
            "SELECT movement_type FROM inventory_ledger WHERE operation_id='s1'"
        ).fetchone()
        assert row["movement_type"] == "SALE_ISSUE"


class TestCanonicalDeduction:
    def _publish_sale(self, conn, op="s1", qty="4"):
        _enable_cutover(conn)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        bus.publish(SALE_ITEMS_PROCESS, {
            "branch_id": "b1", "operation_id": op, "sale_id": "S1", "user": "cashier",
            "items": [{"product_id": "p1", "qty": qty, "es_compuesto": 0}]})

    def test_idempotent_replay(self, conn):
        _seed(conn, qty="10")
        self._publish_sale(conn, op="s1", qty="4")
        self._publish_sale(conn, op="s1", qty="4")  # replay same operation_id
        assert _available(conn) == Decimal("6")  # deducted once, not twice

    def test_oversell_raises_and_rolls_back(self, conn):
        _seed(conn, qty="3")
        _enable_cutover(conn)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        with pytest.raises(RuntimeError):
            bus.publish(SALE_ITEMS_PROCESS, {
                "branch_id": "b1", "operation_id": "s1", "sale_id": "S1",
                "items": [{"product_id": "p1", "qty": "5", "es_compuesto": 0}]})
        assert _available(conn) == Decimal("3")  # unchanged

    def test_does_not_commit_the_sale_transaction(self, conn):
        """The bridge joins the sale's transaction; it must NOT commit on its own
        so the outer sale owns the boundary (legacy auto_commit=False contract)."""
        _enable_cutover(conn)   # commits the flag + seed BEFORE the outer tx opens
        _seed(conn, qty="10")
        conn.commit()  # baseline committed
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        conn.execute("CREATE TABLE _sentinel (v TEXT)")  # opens the outer tx
        # start an outer transaction: insert a sentinel, then run the deduction
        conn.execute("INSERT INTO _sentinel VALUES ('pending')")
        bus.publish(SALE_ITEMS_PROCESS, {
            "branch_id": "b1", "operation_id": "s1", "sale_id": "S1",
            "items": [{"product_id": "p1", "qty": "4", "es_compuesto": 0}]})
        # roll back the whole outer transaction (as a failed sale would)
        conn.rollback()
        # the stock deduction must be gone → bridge did not commit prematurely
        assert conn.execute("SELECT COUNT(*) FROM inventory_ledger"
                            " WHERE operation_id='s1'").fetchone()[0] == 0
        assert _available(conn) == Decimal("10")
