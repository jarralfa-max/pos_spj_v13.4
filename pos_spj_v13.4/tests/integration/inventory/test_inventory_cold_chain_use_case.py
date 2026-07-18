"""INV-9 — cold chain use case + persistence (record reading, excursion, auto-block)."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.use_cases import (
    RecordTemperatureReadingUseCase,
    RegisterInventoryLotUseCase,
)
from backend.domain.inventory.enums import (
    LotOrigin,
    LotQualityStatus,
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
