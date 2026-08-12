"""INV-9 — ResolveTemperatureExcursionUseCase e2e: release/reject the
auto-blocked lot (delegating to SetLotQualityStatusUseCase) and close the
excursion, plus the query-service `id` needed to target one for resolution."""

from decimal import Decimal

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.queries.cold_chain_query_service import (
    ColdChainQueryService,
)
from backend.application.inventory.use_cases import (
    RecordTemperatureReadingUseCase,
    RegisterInventoryLotUseCase,
    ResolveTemperatureExcursionUseCase,
)
from backend.domain.inventory.enums import LotOrigin, LotQualityStatus, TemperaturePoint
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


def _record(conn, temp, *, lot_id=None, auto_block=False, op="rd-1"):
    return RecordTemperatureReadingUseCase().execute(
        conn, sensor_id="s1", warehouse_id="w1", temperature=Decimal(str(temp)),
        reading_point=TemperaturePoint.STORAGE, min_temp=Decimal("0"),
        max_temp=Decimal("4"), warning_margin=Decimal("1"), operation_id=op,
        actor_user_id="u1", lot_id=lot_id, auto_block=auto_block)


def _open_excursion_id(conn):
    with InventoryUnitOfWork(conn) as uow:
        rows = uow.cold_chain.list_open_excursions()
    return rows[0]["id"]


def _lot(conn, *, code="L-1"):
    reg = RegisterInventoryLotUseCase().execute(
        conn, product_id="p1", lot_code=code, origin_type=LotOrigin.PURCHASE,
        operation_id=f"lot-{code}", actor_user_id="u1")
    return reg.entity_id


class TestWarnOnlyResolution:
    def test_resolve_without_lot_just_closes_the_excursion(self, conn):
        _record(conn, "4.5")  # WARNING, no lot
        eid = _open_excursion_id(conn)
        r = ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1", resolution_note="Sólo alerta, sin lote")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.cold_chain.list_open_excursions() == []
            exc = uow.cold_chain.get_excursion(eid)
            assert exc.resolved and exc.resolved_by_user_id == "quality-1"


class TestQuarantineResolution:
    def test_resolve_release_frees_the_lot(self, conn):
        lot_id = _lot(conn)
        _record(conn, "9", lot_id=lot_id, auto_block=True)
        eid = _open_excursion_id(conn)
        r = ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1", resolution_note="Inspección OK")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.lots.get(lot_id).quality_status is LotQualityStatus.RELEASED
            assert uow.cold_chain.get_excursion(eid).resolved

    def test_resolve_reject_writes_off_the_lot(self, conn):
        lot_id = _lot(conn)
        _record(conn, "9", lot_id=lot_id, auto_block=True)
        eid = _open_excursion_id(conn)
        r = ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id=eid, resolution="REJECT", operation_id="rv-1",
            actor_user_id="quality-1", resolution_note="Rotura de cadena de frío")
        assert r.success
        with InventoryUnitOfWork(conn) as uow:
            assert uow.lots.get(lot_id).quality_status is LotQualityStatus.REJECTED

    def test_resolved_excursion_drops_out_of_open_list(self, conn):
        lot_id = _lot(conn)
        _record(conn, "9", lot_id=lot_id, auto_block=True)
        eid = _open_excursion_id(conn)
        ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1")
        assert ColdChainQueryService(conn).list_open_excursions() == []


class TestIdempotencyAndNotFound:
    def test_excursion_not_found(self, conn):
        r = ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id="nope", resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1")
        assert not r.success and r.error_code == "EXCURSION_NOT_FOUND"

    def test_already_resolved_is_idempotent(self, conn):
        _record(conn, "4.5")
        eid = _open_excursion_id(conn)
        first = ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1")
        second = ResolveTemperatureExcursionUseCase().execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-2",
            actor_user_id="quality-1")
        assert first.success and second.success
        assert second.data.get("already_processed") is True


class TestPermissions:
    def test_temperature_resolve_denied(self, conn):
        class Deny:
            def has_permission(self, u, p):
                return False
        _record(conn, "4.5")
        eid = _open_excursion_id(conn)
        r = ResolveTemperatureExcursionUseCase(InventoryAuthorizationPolicy(Deny())).execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"

    def test_lot_release_denial_is_propagated(self, conn):
        class AllowResolveOnly:
            def has_permission(self, u, p):
                return p != InventoryPermissions.LOT_RELEASE
        lot_id = _lot(conn)
        _record(conn, "9", lot_id=lot_id, auto_block=True)
        eid = _open_excursion_id(conn)
        r = ResolveTemperatureExcursionUseCase(
            InventoryAuthorizationPolicy(AllowResolveOnly())).execute(
            conn, excursion_id=eid, resolution="RELEASE", operation_id="rv-1",
            actor_user_id="quality-1")
        assert not r.success and r.error_code == "PERMISSION_DENIED"
        with InventoryUnitOfWork(conn) as uow:
            # el lote no debe quedar liberado, y la excursión sigue abierta
            assert uow.lots.get(lot_id).quality_status is LotQualityStatus.QUARANTINED
            assert not uow.cold_chain.get_excursion(eid).resolved
