"""SET-12 — "Routing": DocumentOutputPrintRoutingClient (real adapter over
device_management's PrintRoute/Device repos + print_routing_policy)
composed with ticket_routing_policy.create_routed_print_job(), against a
real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.exceptions import NoAvailablePrinterError, PrintRouteNotFoundError
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.document_output.policies.ticket_routing_policy import create_routed_print_job
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import (
    SqliteDeviceRepository,
)
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.integrations.document_output_print_routing_client import (
    DocumentOutputPrintRoutingClient,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def client(conn):
    return DocumentOutputPrintRoutingClient(
        SqlitePrintRouteRepository(conn), SqliteDeviceRepository(conn),
    )


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


def _printer(conn, *, active: bool = True):
    branch_id = _existing_branch_id(conn)
    profile = DeviceProfile.create(
        name="Impresora térmica", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=f"PRN-{new_uuid()}", name="Impresora")
    if not active:
        device.enter_maintenance()
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


class TestResolve:
    def test_resolves_active_primary_device(self, conn, client):
        device = _printer(conn)
        route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=device.id)
        SqlitePrintRouteRepository(conn).save(route)
        conn.commit()

        resolution = client.resolve("SALE_TICKET")
        assert resolution.print_route_id == route.id
        assert resolution.printer_device_id == device.id

    def test_fails_over_to_fallback_when_primary_inactive(self, conn, client):
        primary = _printer(conn, active=False)
        fallback = _printer(conn)
        route = PrintRoute.create(
            document_type="SALE_TICKET", primary_device_id=primary.id, fallback_device_ids=(fallback.id,),
        )
        SqlitePrintRouteRepository(conn).save(route)
        conn.commit()

        resolution = client.resolve("SALE_TICKET")
        assert resolution.printer_device_id == fallback.id

    def test_most_specific_route_wins(self, conn, client):
        branch_id = _existing_branch_id(conn)
        global_device = _printer(conn)
        branch_device = _printer(conn)
        SqlitePrintRouteRepository(conn).save(PrintRoute.create(
            document_type="SALE_TICKET", primary_device_id=global_device.id,
        ))
        SqlitePrintRouteRepository(conn).save(PrintRoute.create(
            document_type="SALE_TICKET", primary_device_id=branch_device.id, branch_id=branch_id,
        ))
        conn.commit()

        resolution = client.resolve("SALE_TICKET", branch_id=branch_id)
        assert resolution.printer_device_id == branch_device.id

    def test_raises_when_no_route_matches(self, conn, client):
        with pytest.raises(PrintRouteNotFoundError):
            client.resolve("SALE_TICKET")

    def test_raises_when_no_device_in_chain_is_available(self, conn, client):
        primary = _printer(conn, active=False)
        route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=primary.id)
        SqlitePrintRouteRepository(conn).save(route)
        conn.commit()

        with pytest.raises(NoAvailablePrinterError):
            client.resolve("SALE_TICKET")


class TestComposedWithTicketRoutingPolicy:
    def test_create_routed_print_job_end_to_end(self, conn, client):
        device = _printer(conn)
        route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=device.id)
        SqlitePrintRouteRepository(conn).save(route)
        conn.commit()

        job = create_routed_print_job(
            client, document_type="sale_ticket", source_module="sales", source_document_id=new_uuid(),
            template_version_id=new_uuid(), requested_by_user_id="cashier-1",
        )
        assert job.print_route_id == route.id
        assert job.printer_device_id == device.id
