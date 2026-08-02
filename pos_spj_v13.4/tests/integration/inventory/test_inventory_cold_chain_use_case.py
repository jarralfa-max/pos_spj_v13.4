"""INV-9 — cold chain use case + persistence (record reading, excursion, auto-block)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.use_cases import (
    PostInventoryMovementUseCase,
    RecordTemperatureReadingUseCase,
    RegisterInventoryLotUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    LotQualityStatus,
    MovementType,
    TemperaturePoint,
)
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


def _record(conn, temp, *, lot_id=None, auto_block=False, op="op-1"):
    return RecordTemperatureReadingUseCase().execute(
        conn, sensor_id="s1", warehouse_id="w1", temperature=Decimal(str(temp)),
        reading_point=TemperaturePoint.STORAGE, min_temp=Decimal("0"),
        max_temp=Decimal("4"), warning_margin=Decimal("1"), operation_id=op,
        actor_user_id="u1", lot_id=lot_id, auto_block=auto_block)


class TestColdChainSchema:
    def test_tables_born_clean(self, conn):
        for table in ("inventory_temperature_readings", "inventory_temperature_excursions"):
            pk = [r for r in conn.execute(f"PRAGMA table_info({table})").fetchall() if r[5]]
            assert pk and "INT" not in (pk[0][2] or "").upper()


class TestRecordReading:
    def test_compliant_no_excursion_no_alert(self, conn):
        res = _record(conn, "2")
        assert res.success and res.data["status"] == "COMPLIANT"
        with InventoryUnitOfWork(conn) as uow:
            assert uow.cold_chain.list_open_excursions() == []
            assert uow.outbox.list_pending() == []

    def test_warning_records_excursion_and_alert(self, conn):
        res = _record(conn, "4.5")
        assert res.data["status"] == "WARNING"
        with InventoryUnitOfWork(conn) as uow:
            assert len(uow.cold_chain.list_open_excursions()) == 1
            assert any(p["event_name"] == "INVENTORY_TEMPERATURE_ALERT"
                       for p in uow.outbox.list_pending())

    def test_out_of_range_without_autoblock_warns_only(self, conn):
        res = _record(conn, "9")
        assert res.data["status"] == "OUT_OF_RANGE" and res.data["action"] == "WARN"

    def test_out_of_range_with_autoblock_quarantines_lot(self, conn):
        RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-op", actor_user_id="u1")
        with InventoryUnitOfWork(conn) as uow:
            lot_id = uow.lots.get_by_code("p1", "L-1").id
        res = _record(conn, "9", lot_id=lot_id, auto_block=True, op="op-2")
        assert res.data["action"] == "QUARANTINE"
        with InventoryUnitOfWork(conn) as uow:
            assert uow.lots.get(lot_id).quality_status is LotQualityStatus.QUARANTINED
            events = {p["event_name"] for p in uow.outbox.list_pending()}
            assert "INVENTORY_LOT_BLOCKED" in events and "INVENTORY_TEMPERATURE_ALERT" in events

    def test_permission_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        res = RecordTemperatureReadingUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, sensor_id="s1", warehouse_id="w1", temperature=Decimal("2"),
            reading_point=TemperaturePoint.STORAGE, min_temp=Decimal("0"),
            max_temp=Decimal("4"), operation_id="op-1", actor_user_id="u1")
        assert not res.success and res.error_code == "PERMISSION_DENIED"


class TestAutoBlockMovesStock:
    """§9.2 — cold-chain auto-block MOVES the lot's stock to the QUARANTINED
    bucket (atomically), not only the inventory_lots.quality_status metadata."""

    def _lot_with_stock(self, conn, qty="10"):
        reg = RegisterInventoryLotUseCase().execute(
            conn, product_id="p1", lot_code="L-1", origin_type=LotOrigin.PURCHASE,
            operation_id="lot-op", actor_user_id="u1", branch_id="b1")
        lot_id = reg.entity_id
        line = InventoryMovementLine.create(product_id="p1", quantity=Decimal(qty),
                                            to_location_id="loc1", lot_id=lot_id)
        mv = InventoryMovement.create(
            movement_type=MovementType.PURCHASE_RECEIPT, branch_id="b1",
            warehouse_id="w1", source_module="procurement",
            source_document_type="GR", source_document_id="gr1",
            operation_id="rcv-1", created_by_user_id="u1", lines=[line])
        PostInventoryMovementUseCase().execute(conn, mv, actor_user_id="u1")
        return lot_id

    def _available(self, conn):
        return InventoryAvailabilityQueryService(conn).get_availability(
            product_id="p1", branch_id="b1").available

    def _bucket(self, conn, lot_id, status):
        with InventoryUnitOfWork(conn) as uow:
            bal = uow.balances.get(product_id="p1", branch_id="b1", warehouse_id="w1",
                                   inventory_status=status, location_id="loc1",
                                   lot_id=lot_id)
            return bal.quantity if bal else Decimal("0")

    def test_autoblock_moves_stock_to_quarantine_bucket(self, conn):
        lot_id = self._lot_with_stock(conn, "10")
        assert self._available(conn) == Decimal("10")
        res = _record(conn, "9", lot_id=lot_id, auto_block=True, op="op-x")
        assert res.data["action"] == "QUARANTINE"
        assert self._available(conn) == Decimal("0")                     # excluido
        assert self._bucket(conn, lot_id, InventoryStatus.QUARANTINED) == Decimal("10")
        assert self._bucket(conn, lot_id, InventoryStatus.AVAILABLE) == Decimal("0")
        with InventoryUnitOfWork(conn) as uow:
            assert uow.lots.get(lot_id).quality_status is LotQualityStatus.QUARANTINED

    def test_warn_only_does_not_move_stock(self, conn):
        # sin auto_block, una lectura fuera de rango no toca el stock
        lot_id = self._lot_with_stock(conn, "10")
        res = _record(conn, "9", lot_id=lot_id, auto_block=False, op="op-y")
        assert res.data["action"] == "WARN"
        assert self._available(conn) == Decimal("10")
        assert self._bucket(conn, lot_id, InventoryStatus.QUARANTINED) == Decimal("0")
