"""INV-27 — flag-gated cutover: wiring, reconciliation, deferred drop guard."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.cutover import (
    CanonicalInventoryCutover,
    InventoryReconciliationService,
    is_cutover_enabled,
)
from backend.application.inventory.use_cases import PostInventoryMovementUseCase
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import MovementType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from migrations.deferred import legacy_inventory_drop


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

    def subscribe(self, event_type, handler, priority=0, label=""):
        self.subs.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type, handler):
        bucket = self.subs.get(event_type, [])
        if handler in bucket:
            bucket.remove(handler)
            return True
        return False

    def publish(self, event_type, payload):
        for h in list(self.subs.get(event_type, [])):
            h(payload)


class TestFlag:
    def test_disabled_by_default(self, conn):
        assert is_cutover_enabled(conn, env={}) is False

    def test_env_enables(self, conn):
        assert is_cutover_enabled(conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"}) is True

    def test_setting_enables(self, conn):
        from backend.infrastructure.db.repositories.inventory.support_repositories import (
            InventorySettingsRepository,
        )
        InventorySettingsRepository(conn).set(setting_key="canonical_cutover_enabled",
                                              setting_value="true")
        conn.commit()
        assert is_cutover_enabled(conn, env={}) is True


class TestWiring:
    def test_disabled_wire_is_noop(self, conn):
        bus = _FakeBus()
        report = CanonicalInventoryCutover(conn, env={}).wire(bus)
        assert report["enabled"] is False and bus.subs == {}

    def test_enabled_wire_subscribes_canonical_and_neutralizes_legacy(self, conn):
        bus = _FakeBus()
        legacy_called = []

        def legacy_sale(payload):
            legacy_called.append(payload)

        bus.subscribe("SALE_CONFIRMED", legacy_sale)
        cut = CanonicalInventoryCutover(conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        report = cut.wire(bus, legacy_handlers=[("SALE_CONFIRMED", legacy_sale)])
        assert report["enabled"] is True
        assert "SALE_CONFIRMED" in report["subscribed"] and report["neutralized"] == 1
        assert "GOODS_RECEIPT_COMPLETED" in report["subscribed"]
        assert legacy_sale not in bus.subs["SALE_CONFIRMED"]  # legacy dropped

    def test_wired_receipt_event_drives_canonical_ledger(self, conn):
        bus = _FakeBus()
        CanonicalInventoryCutover(conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"}).wire(bus)
        bus.publish("GOODS_RECEIPT_COMPLETED", {
            "operation_id": "gr-1", "branch_id": "b1", "warehouse_id": "w1",
            "goods_receipt_id": "GR-1", "user_id": "u1",
            "lines": [{"product_id": "p1", "quantity": "10", "to_location_id": "loc1"}]})
        row = conn.execute(
            "SELECT movement_type FROM inventory_ledger WHERE operation_id='gr-1'").fetchone()
        assert row["movement_type"] == "PURCHASE_RECEIPT"

    def test_unwire_removes_subscriptions(self, conn):
        bus = _FakeBus()
        cut = CanonicalInventoryCutover(conn, env={"INVENTORY_CANONICAL_CUTOVER": "1"})
        cut.wire(bus)
        assert cut.unwire(bus) >= 1
        assert all(not v for v in bus.subs.values())


class TestReconciliation:
    def _seed_canonical(self, conn, qty="10"):
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                            to_location_id="loc1")
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
            source_module="procurement", source_document_type="GR", source_document_id="g1",
            operation_id="g1", created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")

    def test_no_legacy_table_reports_canonical_only(self, conn):
        self._seed_canonical(conn)
        svc = InventoryReconciliationService(conn)
        rows = svc.reconcile()
        assert len(rows) == 1 and rows[0].canonical == Decimal("10")
        assert rows[0].legacy == Decimal("0")
        assert svc.is_in_sync() is False  # no legacy source → cannot confirm parity

    def test_parity_and_drift_against_legacy(self, conn):
        self._seed_canonical(conn, "10")
        conn.execute("CREATE TABLE inventario_actual (producto_id TEXT, sucursal_id TEXT,"
                     " cantidad TEXT)")
        conn.execute("INSERT INTO inventario_actual VALUES ('p1','b1','10')")
        conn.commit()
        svc = InventoryReconciliationService(conn)
        assert svc.is_in_sync() is True and svc.drifts() == []
        conn.execute("UPDATE inventario_actual SET cantidad='7' WHERE producto_id='p1'")
        conn.commit()
        drifts = svc.drifts()
        assert len(drifts) == 1 and drifts[0].drift == Decimal("3")


class TestDeferredDrop:
    def test_refuses_without_env_guard(self, conn):
        with pytest.raises(RuntimeError):
            legacy_inventory_drop.run(conn, env={})

    def test_drops_legacy_when_guard_set(self, conn):
        conn.execute("CREATE TABLE inventario_actual (producto_id TEXT)")
        conn.execute("CREATE TABLE transferencias (id TEXT)")
        conn.commit()
        result = legacy_inventory_drop.run(conn, env={"INVENTORY_ALLOW_LEGACY_DROP": "1"})
        assert "inventario_actual" in result["tables"]
        remaining = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "inventario_actual" not in remaining and "transferencias" not in remaining
        # canonical ledger untouched
        assert "inventory_ledger" in remaining

    def test_not_registered_in_engine(self):
        from migrations.engine import MIGRATIONS
        modules = {m.module for m in MIGRATIONS}
        assert "migrations.deferred.legacy_inventory_drop" not in modules
