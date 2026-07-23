"""INV-27 FLIP (producción) — the live PRODUCTION_ITEMS_PROCESS movements switch
from the legacy inventory engine to canonical PRODUCTION_CONSUMPTION /
PRODUCTION_OUTPUT movements on the ledger.

``_wire_production_items_handlers`` selects exactly ONE handler by the cutover
flag. With the flag ON the canonical bridge splits the flat ``movements`` list by
delta sign (consume vs output), posts inside the production transaction (no
premature commit), and is idempotent by derived operation_id.
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
from core.events.domain_events import PRODUCTION_ITEMS_PROCESS


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
    def __init__(self, db, finance_service=None):
        self.db = db
        self.finance_service = finance_service


def _enable_cutover(conn):
    InventorySettingsRepository(conn).set(
        setting_key="canonical_cutover_enabled", setting_value="true")
    conn.commit()


def _seed(conn, product_id, qty, branch_id="b1"):
    line = InventoryMovementLine.create(
        product_id=product_id, quantity=Decimal(qty), to_location_id=branch_id,
        reason_code="OPENING")
    mv = InventoryMovement.create(
        movement_type=MovementType.ADJUSTMENT_IN, branch_id=branch_id,
        warehouse_id=branch_id, source_module="test", source_document_type="SEED",
        source_document_id="seed", operation_id=f"seed:{product_id}",
        created_by_user_id="system", lines=[line])
    PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="system")


def _available(conn, product_id, branch_id="b1"):
    return InventoryAvailabilityQueryService(conn).get_availability(
        product_id=product_id, branch_id=branch_id).available


def _wire(bus, container):
    from core.events.wiring import _wire_production_items_handlers
    _wire_production_items_handlers(bus, container)


def _prod_payload(op="prod-1"):
    # consume 3 of raw p1, output 2 of finished p2
    return {"branch_id": "b1", "operation_id": op, "reference_id": "PROD-1",
            "user": "produccion",
            "movements": [
                {"product_id": "p1", "delta": -3, "movement_type": "PRODUCCION"},
                {"product_id": "p2", "delta": 2, "movement_type": "PRODUCCION"}]}


class TestFlagSelectsHandler:
    def test_wires_canonical_handler(self, conn):
        # corte INV-27: wiring canónico incondicional (motor legacy eliminado)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        assert bus.labels[PRODUCTION_ITEMS_PROCESS] == ["production_inventory_handler"]

    def test_flag_on_posts_canonical_consumption_and_output(self, conn):
        _enable_cutover(conn)
        _seed(conn, "p1", "10")
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        bus.publish(PRODUCTION_ITEMS_PROCESS, _prod_payload())
        assert _available(conn, "p1") == Decimal("7")   # consumed 3
        assert _available(conn, "p2") == Decimal("2")   # produced 2
        types = {r["movement_type"] for r in conn.execute(
            "SELECT movement_type FROM inventory_ledger").fetchall()}
        assert "PRODUCTION_CONSUMPTION" in types and "PRODUCTION_OUTPUT" in types


class TestCanonicalMovements:
    def _run(self, conn, payload):
        _enable_cutover(conn)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        bus.publish(PRODUCTION_ITEMS_PROCESS, payload)

    def test_idempotent_replay(self, conn):
        _seed(conn, "p1", "10")
        _enable_cutover(conn)
        bus = _FakeBus()
        _wire(bus, _Container(conn))
        bus.publish(PRODUCTION_ITEMS_PROCESS, _prod_payload(op="prod-1"))
        bus.publish(PRODUCTION_ITEMS_PROCESS, _prod_payload(op="prod-1"))  # replay
        assert _available(conn, "p1") == Decimal("7")   # consumed once
        assert _available(conn, "p2") == Decimal("2")   # produced once

    def test_uses_payload_conn_when_present(self, conn):
        """The production flow shares its transaction via payload['conn']; the
        bridge must use it (and must not commit — outer flow owns the boundary)."""
        _enable_cutover(conn)
        _seed(conn, "p1", "10")
        conn.commit()
        bus = _FakeBus()
        # provider returns None → bridge must fall back to payload['conn']
        from backend.application.event_handlers.inventory.production_items_bridge import (
            CanonicalProductionInventoryHandler,
        )
        handler = CanonicalProductionInventoryHandler(lambda: None)
        payload = _prod_payload()
        payload["conn"] = conn
        conn.execute("CREATE TABLE _sentinel (v TEXT)")  # opens outer tx
        handler.handle(payload)
        conn.rollback()  # abort the whole production tx
        # the production movements are gone (seed opening balance stays committed)
        assert conn.execute("SELECT COUNT(*) FROM inventory_ledger"
                            " WHERE operation_id LIKE 'prod-1:%'").fetchone()[0] == 0
        assert _available(conn, "p1") == Decimal("10")  # rolled back
