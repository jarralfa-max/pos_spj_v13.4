"""INV-4 — inventory repositories + atomic UnitOfWork.

Ledger persistence + idempotency, balance projection upsert/read (None ↔ ''),
warehouses/zones/locations, configurable limits with scope precedence, the
support repos (authorization/audit/outbox/processed/settings), and the UoW
transaction boundary (all-or-nothing commit, rollback on exception).
"""

from decimal import Decimal

import sqlite3

import pytest

from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.entities.warehouse import (
    StorageLocation,
    Warehouse,
    WarehouseZone,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementType,
    WarehouseType,
    WarehouseZoneType,
)
from backend.domain.inventory.value_objects.authorization_grant import AuthorizationGrant
from backend.domain.inventory.value_objects.inventory_limit import InventoryOperationLimit
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _movement(op="op-1"):
    line = InventoryMovementLine.create(
        product_id="p1", quantity=Decimal("25"), weight=Decimal("58.750"),
        unit="KG", to_location_id="loc1")
    return InventoryMovement.create(
        movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1", warehouse_id="w1",
        source_module="procurement", source_document_type="GOODS_RECEIPT",
        source_document_id="gr1", operation_id=op, created_by_user_id="u1", lines=[line])


# ── ledger ──────────────────────────────────────────────────────────────────
class TestLedgerRepository:
    def test_save_and_idempotency_lookup(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            mv = _movement("op-1")
            uow.ledger.save(mv)
        with InventoryUnitOfWork(conn) as uow:
            found = uow.ledger.find_by_operation_id("op-1")
            assert found is not None and found["movement_type"] == "PURCHASE_RECEIPT"
            assert uow.ledger.find_by_operation_id("op-nope") is None
            lines = uow.ledger.get_lines(found["id"])
            assert len(lines) == 1 and lines[0]["weight"] == "58.750"

    def test_duplicate_operation_id_raises(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            uow.ledger.save(_movement("dup"))
        with pytest.raises(sqlite3.IntegrityError):
            with InventoryUnitOfWork(conn) as uow:
                mv = _movement("dup")  # same operation_id
                uow.ledger.save(mv)


# ── balance projection ──────────────────────────────────────────────────────
class TestBalanceRepository:
    def test_upsert_and_read_roundtrip_none_maps_to_empty(self, conn):
        bal = InventoryBalance.empty(product_id="p1", branch_id="b1", warehouse_id="w1")
        bal.apply_delta(quantity=Decimal("10"))
        with InventoryUnitOfWork(conn) as uow:
            uow.balances.upsert(bal)
        with InventoryUnitOfWork(conn) as uow:
            got = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1")
            assert got is not None
            assert got.quantity == Decimal("10")
            assert got.location_id is None and got.lot_id is None  # '' → None

    def test_upsert_is_idempotent_on_dimension(self, conn):
        bal = InventoryBalance.empty(product_id="p1", branch_id="b1", warehouse_id="w1")
        bal.apply_delta(quantity=Decimal("5"))
        with InventoryUnitOfWork(conn) as uow:
            uow.balances.upsert(bal)
        bal.apply_delta(quantity=Decimal("7"))  # now 12, version bumped
        with InventoryUnitOfWork(conn) as uow:
            uow.balances.upsert(bal)  # same dimension → update, not a 2nd row
        with InventoryUnitOfWork(conn) as uow:
            rows = uow.balances.list_by_product_branch("p1", "b1")
            assert len(rows) == 1 and rows[0]["quantity"] == "12"


# ── warehouses ──────────────────────────────────────────────────────────────
class TestWarehouseRepository:
    def test_save_warehouse_zone_location(self, conn):
        wh = Warehouse.create(code="CD01", name="Central", branch_id="b1",
                              warehouse_type=WarehouseType.CENTRAL)
        zone = WarehouseZone.create(warehouse_id=wh.id, code="COLD", name="Cámara",
                                    zone_type=WarehouseZoneType.COLD)
        loc = StorageLocation.create(warehouse_id=wh.id, zone_id=zone.id,
                                     code="A-01", name="Rack A", level=1)
        with InventoryUnitOfWork(conn) as uow:
            uow.warehouses.save_warehouse(wh)
            uow.warehouses.save_zone(zone)
            uow.warehouses.save_location(loc)
        with InventoryUnitOfWork(conn) as uow:
            assert uow.warehouses.get_by_code("CD01")["name"] == "Central"
            assert len(uow.warehouses.list_zones(wh.id)) == 1
            assert uow.warehouses.get_location(loc.id)["code"] == "A-01"


# ── limits ──────────────────────────────────────────────────────────────────
class TestLimitRepository:
    def test_upsert_get_and_scope_precedence(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            uow.limits.upsert_limit(
                scope_type="BRANCH", scope_id="b1", operation_kind="ADJUSTMENT",
                limit=InventoryOperationLimit(approval_threshold=Decimal("10"),
                                              hard_cap=Decimal("100")))
            uow.limits.upsert_limit(
                scope_type="USER", scope_id="u1", operation_kind="ADJUSTMENT",
                limit=InventoryOperationLimit(approval_threshold=Decimal("5"),
                                              hard_cap=Decimal("50")))
        with InventoryUnitOfWork(conn) as uow:
            branch = uow.limits.get_limit(scope_type="BRANCH", scope_id="b1",
                                          operation_kind="ADJUSTMENT")
            assert branch.hard_cap == Decimal("100")
            # USER scope wins over BRANCH in resolution
            resolved = uow.limits.resolve(operation_kind="ADJUSTMENT", user_id="u1",
                                          branch_id="b1")
            assert resolved.hard_cap == Decimal("50")
            # falls back to BRANCH when no USER limit
            resolved2 = uow.limits.resolve(operation_kind="ADJUSTMENT", user_id="uX",
                                           branch_id="b1")
            assert resolved2.hard_cap == Decimal("100")


# ── support repositories ────────────────────────────────────────────────────
class TestSupportRepositories:
    def test_authorization_and_audit_and_outbox_and_processed(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            uow.authorization_log.record(AuthorizationGrant(
                permission_code="INVENTORY_ADJUSTMENT_APPROVE", requested_by="u1",
                authorized_by="boss", operation_id="op-1", reason="crítico",
                quantity=Decimal("5")))
            uow.audit.record(entity_type="MOVEMENT", entity_id="mv1", action="POSTED",
                             user_id="u1", operation_id="op-1", product_id="p1")
            uow.outbox.enqueue(event_id="e1", event_name="INVENTORY_MOVEMENT_POSTED",
                               payload_json="{}", operation_id="op-1")
            uow.processed_events.mark_processed("e1", "INVENTORY_MOVEMENT_POSTED", "op-1")
        with InventoryUnitOfWork(conn) as uow:
            assert len(uow.audit.list_for_entity("MOVEMENT", "mv1")) == 1
            pending = uow.outbox.list_pending()
            assert len(pending) == 1 and pending[0]["event_name"] == "INVENTORY_MOVEMENT_POSTED"
            assert uow.processed_events.was_processed("e1") is True
            uow.outbox.mark_dispatched(pending[0]["id"])
        with InventoryUnitOfWork(conn) as uow:
            assert uow.outbox.list_pending() == []

    def test_settings_get_set(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            uow.settings.set(setting_key="negative_inventory_allowed", setting_value="false")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.settings.get(setting_key="negative_inventory_allowed") == "false"
            assert uow.settings.get(setting_key="missing") is None


# ── UoW atomicity ───────────────────────────────────────────────────────────
class TestUnitOfWorkAtomicity:
    def test_commit_persists_ledger_and_outbox_together(self, conn):
        with InventoryUnitOfWork(conn) as uow:
            uow.ledger.save(_movement("atomic-ok"))
            uow.outbox.enqueue(event_id="e1", event_name="INVENTORY_MOVEMENT_POSTED",
                               payload_json="{}", operation_id="atomic-ok")
        # clean exit → both committed
        rows = conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0]
        outbox = conn.execute("SELECT COUNT(*) FROM inventory_outbox").fetchone()[0]
        assert rows == 1 and outbox == 1

    def test_exception_rolls_back_everything(self, conn):
        with pytest.raises(RuntimeError):
            with InventoryUnitOfWork(conn) as uow:
                uow.ledger.save(_movement("atomic-fail"))
                uow.outbox.enqueue(event_id="e2", event_name="INVENTORY_MOVEMENT_POSTED",
                                   payload_json="{}", operation_id="atomic-fail")
                raise RuntimeError("boom")
        assert conn.execute("SELECT COUNT(*) FROM inventory_ledger").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM inventory_outbox").fetchone()[0] == 0
