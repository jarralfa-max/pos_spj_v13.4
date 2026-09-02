"""SET-8 follow-up — real CRUD for "Rutas de impresión" (PrintRoute:
which device a document_type prints to, with an ordered fallback
chain). Against a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.print_route_use_cases import (
    ChangePrintRouteStatusUseCase,
    CreatePrintRouteUseCase,
    PrintRouteStatusAction,
    UpdatePrintRouteUseCase,
)
from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.exceptions import PrintRouteConflictError, PrintRouteNotFoundError
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def branch_id(conn):
    existing = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()
    if existing:
        return existing[0]
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal Test"))
    conn.commit()
    return branch_id


def _saved_printer(conn, branch_id, code="PRN-01") -> Device:
    profile = DeviceProfile.create(
        name=f"Printer {code}", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=code, name=f"Impresora {code}")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


class TestCreatePrintRouteUseCase:
    def test_creates_a_global_route(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        use_case = CreatePrintRouteUseCase(conn)
        route = use_case.execute(document_type="sale_ticket", primary_device_id=primary.id)
        assert route.document_type == "SALE_TICKET"
        fetched = SqlitePrintRouteRepository(conn).get(route.id)
        assert fetched.primary_device_id == primary.id

    def test_creates_with_fallback_chain(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        fallback = _saved_printer(conn, branch_id, "PRN-02")
        route = CreatePrintRouteUseCase(conn).execute(
            document_type="SALE_TICKET", primary_device_id=primary.id, fallback_device_ids=(fallback.id,),
        )
        assert route.fallback_device_ids == (fallback.id,)

    def test_rejects_exact_scope_conflict(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        other = _saved_printer(conn, branch_id, "PRN-02")
        use_case = CreatePrintRouteUseCase(conn)
        use_case.execute(document_type="SALE_TICKET", primary_device_id=primary.id)
        with pytest.raises(PrintRouteConflictError):
            use_case.execute(document_type="SALE_TICKET", primary_device_id=other.id)

    def test_rejects_conflict_even_when_existing_route_is_inactive(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        other = _saved_printer(conn, branch_id, "PRN-02")
        use_case = CreatePrintRouteUseCase(conn)
        route = use_case.execute(document_type="SALE_TICKET", primary_device_id=primary.id)
        ChangePrintRouteStatusUseCase(conn).execute(route_id=route.id, action=PrintRouteStatusAction.DEACTIVATE)
        # The schema's unique index covers the row regardless of `active` —
        # a deactivated route still occupies its exact scope.
        with pytest.raises(PrintRouteConflictError):
            use_case.execute(document_type="SALE_TICKET", primary_device_id=other.id)

    def test_different_branch_scope_does_not_conflict(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        other = _saved_printer(conn, branch_id, "PRN-02")
        other_branch_id = new_uuid()
        conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (other_branch_id, "Otra sucursal"))
        conn.commit()
        use_case = CreatePrintRouteUseCase(conn)
        use_case.execute(document_type="SALE_TICKET", primary_device_id=primary.id, branch_id=branch_id)
        route2 = use_case.execute(
            document_type="SALE_TICKET", primary_device_id=other.id, branch_id=other_branch_id,
        )
        assert route2.branch_id == other_branch_id


class TestUpdatePrintRouteUseCase:
    def test_updates_primary_and_fallback(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        fallback = _saved_printer(conn, branch_id, "PRN-02")
        route = CreatePrintRouteUseCase(conn).execute(document_type="SALE_TICKET", primary_device_id=primary.id)
        updated = UpdatePrintRouteUseCase(conn).execute(
            route_id=route.id, primary_device_id=primary.id, fallback_device_ids=(fallback.id,),
        )
        assert updated.fallback_device_ids == (fallback.id,)

    def test_promotes_a_fallback_device_to_primary(self, conn, branch_id):
        # Real bug caught by manual smoke-testing: set_primary_device()
        # validates against the CURRENT fallback list, so naively calling
        # set_primary_device() before set_fallback_chain() rejects
        # promoting a device straight out of fallback into primary.
        primary = _saved_printer(conn, branch_id, "PRN-01")
        fallback = _saved_printer(conn, branch_id, "PRN-02")
        route = CreatePrintRouteUseCase(conn).execute(
            document_type="SALE_TICKET", primary_device_id=primary.id, fallback_device_ids=(fallback.id,),
        )
        updated = UpdatePrintRouteUseCase(conn).execute(route_id=route.id, primary_device_id=fallback.id)
        assert updated.primary_device_id == fallback.id
        assert updated.fallback_device_ids == ()

    def test_unknown_route_raises(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        with pytest.raises(PrintRouteNotFoundError):
            UpdatePrintRouteUseCase(conn).execute(route_id=new_uuid(), primary_device_id=primary.id)


class TestChangePrintRouteStatusUseCase:
    def test_deactivate_and_activate(self, conn, branch_id):
        primary = _saved_printer(conn, branch_id, "PRN-01")
        route = CreatePrintRouteUseCase(conn).execute(document_type="SALE_TICKET", primary_device_id=primary.id)
        use_case = ChangePrintRouteStatusUseCase(conn)

        deactivated = use_case.execute(route_id=route.id, action=PrintRouteStatusAction.DEACTIVATE)
        assert deactivated.active is False

        activated = use_case.execute(route_id=route.id, action=PrintRouteStatusAction.ACTIVATE)
        assert activated.active is True

    def test_unknown_route_raises(self, conn):
        use_case = ChangePrintRouteStatusUseCase(conn)
        with pytest.raises(PrintRouteNotFoundError):
            use_case.execute(route_id=new_uuid(), action=PrintRouteStatusAction.ACTIVATE)
