"""SET-8 — PrintRoute / PrinterTestResult infrastructure repositories
against a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.entities.printer_test_result import PrinterTestResult
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.policies.print_routing_policy import resolve_route, select_device
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.db.repositories.device_management.printer_test_result_repository import (
    SqlitePrinterTestResultRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def route_repo(conn):
    return SqlitePrintRouteRepository(conn)


@pytest.fixture
def test_result_repo(conn):
    return SqlitePrinterTestResultRepository(conn)


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


def _existing_workstation_id(conn, branch_id: str) -> str:
    workstation = Workstation.create(
        branch_id=branch_id, code=f"POS-{new_uuid()[:8]}", name="Caja", workstation_type=WorkstationType.POS,
    )
    SqliteWorkstationRepository(conn).save(workstation)
    return workstation.id


def _existing_device(conn, branch_id: str, code: str) -> Device:
    profile_repo = SqliteDeviceProfileRepository(conn)
    profile = DeviceProfile.create(
        name=f"Impresora {code}", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    profile_repo.save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=code, name=f"Impresora {code}")
    SqliteDeviceRepository(conn).save(device)
    return device


class TestPrintRouteRepository:
    def test_round_trips_all_fields(self, conn, route_repo):
        branch_id = _existing_branch_id(conn)
        workstation_id = _existing_workstation_id(conn, branch_id)
        primary = _existing_device(conn, branch_id, "PRN-01")
        fallback = _existing_device(conn, branch_id, "PRN-02")
        conn.commit()

        route = PrintRoute.create(
            document_type="sale_ticket", primary_device_id=primary.id, fallback_device_ids=(fallback.id,),
            branch_id=branch_id, workstation_id=workstation_id, module="ventas", channel="pos",
        )
        route_repo.save(route)
        conn.commit()

        fetched = route_repo.get(route.id)
        assert fetched.document_type == "SALE_TICKET"
        assert fetched.primary_device_id == primary.id
        assert fetched.fallback_device_ids == (fallback.id,)
        assert fetched.branch_id == branch_id
        assert fetched.workstation_id == workstation_id
        assert fetched.module == "ventas"
        assert fetched.channel == "pos"

    def test_global_route_round_trips_none_scope(self, conn, route_repo):
        branch_id = _existing_branch_id(conn)
        primary = _existing_device(conn, branch_id, "PRN-01")
        conn.commit()
        route = PrintRoute.create(document_type="label", primary_device_id=primary.id)
        route_repo.save(route)
        conn.commit()
        fetched = route_repo.get(route.id)
        assert fetched.branch_id is None
        assert fetched.workstation_id is None

    def test_primary_device_id_must_reference_existing_device(self, conn, route_repo):
        orphan = PrintRoute.create(document_type="sale_ticket", primary_device_id=new_uuid())
        with pytest.raises(sqlite3.IntegrityError):
            route_repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_duplicate_exact_scope_route_rejected(self, conn, route_repo):
        branch_id = _existing_branch_id(conn)
        device_a = _existing_device(conn, branch_id, "PRN-01")
        device_b = _existing_device(conn, branch_id, "PRN-02")
        conn.commit()

        route_repo.save(PrintRoute.create(document_type="sale_ticket", primary_device_id=device_a.id, branch_id=branch_id))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            route_repo.save(PrintRoute.create(document_type="sale_ticket", primary_device_id=device_b.id, branch_id=branch_id))
            conn.commit()
        conn.rollback()

    def test_same_document_type_different_scope_is_allowed(self, conn, route_repo):
        branch_id_a, branch_id_b = _existing_branch_id(conn), _existing_branch_id(conn)
        device_a = _existing_device(conn, branch_id_a, "PRN-01")
        device_b = _existing_device(conn, branch_id_b, "PRN-02")
        conn.commit()

        route_repo.save(PrintRoute.create(document_type="sale_ticket", primary_device_id=device_a.id, branch_id=branch_id_a))
        route_repo.save(PrintRoute.create(document_type="sale_ticket", primary_device_id=device_b.id, branch_id=branch_id_b))
        conn.commit()  # must not collide — different branch scope

        assert len(route_repo.list_candidates("sale_ticket")) == 2

    def test_list_candidates_and_resolve_route_end_to_end(self, conn, route_repo):
        branch_id = _existing_branch_id(conn)
        global_device = _existing_device(conn, branch_id, "PRN-GLOBAL")
        branch_device = _existing_device(conn, branch_id, "PRN-BRANCH")
        conn.commit()

        route_repo.save(PrintRoute.create(document_type="sale_ticket", primary_device_id=global_device.id))
        route_repo.save(PrintRoute.create(document_type="sale_ticket", primary_device_id=branch_device.id, branch_id=branch_id))
        conn.commit()

        candidates = route_repo.list_candidates("sale_ticket")
        resolved = resolve_route("SALE_TICKET", candidates, branch_id=branch_id)
        assert resolved.primary_device_id == branch_device.id

        selection = select_device(resolved, is_available=lambda device_id: True)
        assert selection.device_id == branch_device.id
        assert selection.used_failover is False

    def test_list_active_excludes_inactive(self, conn, route_repo):
        branch_id = _existing_branch_id(conn)
        device = _existing_device(conn, branch_id, "PRN-01")
        conn.commit()
        active = PrintRoute.create(document_type="sale_ticket", primary_device_id=device.id)
        inactive = PrintRoute.create(document_type="label", primary_device_id=device.id)
        inactive.deactivate()
        route_repo.save(active)
        route_repo.save(inactive)
        conn.commit()
        assert [r.id for r in route_repo.list_active()] == [active.id]


class TestPrinterTestResultRepository:
    def test_round_trips_and_orders_most_recent_first(self, conn, test_result_repo):
        branch_id = _existing_branch_id(conn)
        device = _existing_device(conn, branch_id, "PRN-01")
        conn.commit()

        now = datetime.now(timezone.utc)
        first = PrinterTestResult.record(device_id=device.id, success=False, message="Sin papel", at=now)
        test_result_repo.save(first)
        conn.commit()
        second = PrinterTestResult.record(
            device_id=device.id, success=True, message="Resuelto", tested_by_user_id="admin-1",
            at=now + timedelta(seconds=1),
        )
        test_result_repo.save(second)
        conn.commit()

        history = test_result_repo.list_for_device(device.id)
        assert [r.id for r in history] == [second.id, first.id]
        assert history[0].tested_by_user_id == "admin-1"

    def test_device_id_must_reference_existing_device(self, conn, test_result_repo):
        orphan = PrinterTestResult.record(device_id=new_uuid(), success=True)
        with pytest.raises(sqlite3.IntegrityError):
            test_result_repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_empty_history_for_unknown_device(self, conn, test_result_repo):
        assert test_result_repo.list_for_device(new_uuid()) == []
