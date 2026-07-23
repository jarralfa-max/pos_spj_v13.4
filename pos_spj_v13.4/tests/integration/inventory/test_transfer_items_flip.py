"""INV-27 FLIP (transferencias) — the live TRANSFER_ITEMS_PROCESS movements switch
from the legacy inventory engine to canonical TRANSFER_DISPATCH / TRANSFER_RECEIPT
movements on the ledger.

``_wire_transfer_items_handlers`` selects exactly ONE handler by the cutover flag.
With the flag ON the canonical bridge groups the flat multi-branch ``movements``
list by (branch, direction), posts inside the transfer transaction (no premature
commit), and is idempotent by derived operation_id.
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
from core.events.domain_events import TRANSFER_ITEMS_PROCESS


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


class _Container:
    def __init__(self, db):
        self.db = db


def _enable_cutover(conn):
    InventorySettingsRepository(conn).set(
        setting_key="canonical_cutover_enabled", setting_value="true")
    conn.commit()


def _seed(conn, product_id, qty, branch_id):
    line = InventoryMovementLine.create(
        product_id=product_id, quantity=Decimal(qty), to_location_id=branch_id,
        reason_code="OPENING")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id=branch_id,
        warehouse_id=branch_id, source_module="test", source_document_type="SEED",
        source_document_id="seed", operation_id=f"seed:{product_id}:{branch_id}",
        created_by_user_id="system", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="system")


def _available(conn, product_id, branch_id):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _wire(bus, container):
    from core.events.wiring import _wire_transfer_items_handlers
    _wire_transfer_items_handlers(bus, container)


def _transfer_payload(op="tr-1"):
    # move 3 of p1 from origin b1 → dest b2 (one publish, two legs)
    return {"transfer_id": "TR-1", "operation_id": op,
            "reference_type": "TRANSFER_DISPATCH", "user": "u1",
            "movements": [
                {"product_id": "p1", "delta": -3, "branch_id": "b1",
                 "movement_type": "TRANSFER_OUT"},
                {"product_id": "p1", "delta": 3, "branch_id": "b2",
                 "movement_type": "TRANSFER_IN"}]}


class TestFlagSelectsHandler:
    def test_wires_canonical_handler(self, conn):
        # corte INV-27: wiring canónico incondicional (motor legacy eliminado)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        assert bus.labels[TRANSFER_ITEMS_PROCESS] == ["transfer_inventory_handler"]

    def test_flag_on_posts_dispatch_and_receipt(self, conn):
        _enable_cutover(conn)
        _seed(conn, "p1", "10", "b1")
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        bus.publish(TRANSFER_ITEMS_PROCESS, _transfer_payload())
        assert _available(conn, "p1", "b1") == Decimal("7")   # dispatched 3
        assert _available(conn, "p1", "b2") == Decimal("3")   # received 3
        types = {r["movement_type"] for r in conn.execute(
            "SELECT movement_type FROM inventory_ledger").fetchall()}
        assert "TRANSFER_DISPATCH" in types and "TRANSFER_RECEIPT" in types


class TestCanonicalTransfer:
    def test_idempotent_replay(self, conn):
        _enable_cutover(conn)
        _seed(conn, "p1", "10", "b1")
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        bus.publish(TRANSFER_ITEMS_PROCESS, _transfer_payload(op="tr-1"))
        bus.publish(TRANSFER_ITEMS_PROCESS, _transfer_payload(op="tr-1"))  # replay
        assert _available(conn, "p1", "b1") == Decimal("7")
        assert _available(conn, "p1", "b2") == Decimal("3")

    def test_uses_payload_conn_and_rolls_back(self, conn):
        _enable_cutover(conn)
        _seed(conn, "p1", "10", "b1")
        conn.commit()
        from backend.application.event_handlers.inventory.transfer_items_bridge import (
            CanonicalTransferInventoryHandler,
        )
        handler = CanonicalTransferInventoryHandler(lambda: None)  # forces payload conn
        payload = _transfer_payload()
        payload["conn"] = conn
        conn.execute("CREATE TABLE _sentinel (v TEXT)")  # opens outer tx
        handler.handle(payload)
        conn.rollback()
        assert conn.execute("SELECT COUNT(*) FROM inventory_ledger"
                            " WHERE operation_id LIKE 'tr-1:%'").fetchone()[0] == 0
        assert _available(conn, "p1", "b1") == Decimal("10")  # rolled back

    def test_dispatch_beyond_stock_raises(self, conn):
        _enable_cutover(conn)
        _seed(conn, "p1", "2", "b1")
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        with pytest.raises(RuntimeError):
            bus.publish(TRANSFER_ITEMS_PROCESS, _transfer_payload())  # dispatch 3 > 2
