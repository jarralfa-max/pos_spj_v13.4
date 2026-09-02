"""SET-12 cutover — SalesPrintJobClient against a real (in-memory) SQLite
schema combining Sales (`sales_schema.py`) with the born-clean Document
Output/Device Management schema (migrations 211/212/214). The central
property under test: this integration is audit/governance-only and must
degrade to `None` — never raise — whenever a prerequisite (template,
active version, print route, available device) is missing, or a prior
job isn't yet reprintable.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.document_output.entities.document_template import DocumentTemplate
from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.enums import DocumentType, PrintJobStatus, RenderFormat
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_repository import (
    SqliteDocumentTemplateRepository,
)
from backend.infrastructure.db.repositories.document_output.document_template_version_repository import (
    SqliteDocumentTemplateVersionRepository,
)
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_print_job_client import SalesPrintJobClient
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    create_sales_schema(connection)
    connection.commit()
    yield connection
    connection.close()


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


def _active_device(conn, branch_id) -> Device:
    profile = DeviceProfile.create(
        name="Impresora térmica", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=f"PRN-{new_uuid()}", name="Impresora")
    SqliteDeviceRepository(conn).save(device)
    return device


def _active_sale_ticket_template(conn) -> None:
    template = DocumentTemplate.create(
        document_type=DocumentType.SALE_TICKET, name="Ticket de venta", module="sales")
    SqliteDocumentTemplateRepository(conn).save(template)
    version = DocumentTemplateVersion.create(
        template_id=template.id, content_format=RenderFormat.ESC_POS, content="<ticket/>")
    version.submit_for_approval()
    version.approve(approved_by_user_id="admin-1")
    version.activate(activated_by_user_id="admin-1")
    SqliteDocumentTemplateVersionRepository(conn).save(version)


def _configure_route(conn, device) -> None:
    route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=device.id)
    SqlitePrintRouteRepository(conn).save(route)


class TestTryCreateOrReprintJob:
    def test_no_template_configured_returns_none(self, conn):
        client = SalesPrintJobClient(conn)
        result = client.try_create_or_reprint_job(
            sale_id=new_uuid(), branch_id=_existing_branch_id(conn), actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        assert result is None

    def test_template_without_route_returns_none(self, conn):
        _active_sale_ticket_template(conn)
        conn.commit()
        client = SalesPrintJobClient(conn)

        result = client.try_create_or_reprint_job(
            sale_id=new_uuid(), branch_id=_existing_branch_id(conn), actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        assert result is None

    def test_route_with_no_available_device_returns_none(self, conn):
        branch_id = _existing_branch_id(conn)
        device = _active_device(conn, branch_id)
        device.enter_maintenance()
        SqliteDeviceRepository(conn).save(device)
        _active_sale_ticket_template(conn)
        _configure_route(conn, device)
        conn.commit()
        client = SalesPrintJobClient(conn)

        result = client.try_create_or_reprint_job(
            sale_id=new_uuid(), branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        assert result is None

    def test_configured_creates_a_real_routed_job(self, conn):
        branch_id = _existing_branch_id(conn)
        device = _active_device(conn, branch_id)
        _active_sale_ticket_template(conn)
        _configure_route(conn, device)
        conn.commit()
        client = SalesPrintJobClient(conn)
        sale_id = new_uuid()

        job = client.try_create_or_reprint_job(
            sale_id=sale_id, branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")

        assert job is not None
        assert job.status is PrintJobStatus.PRINTING
        assert job.printer_device_id == device.id
        assert job.source_module == "sales"
        assert job.source_document_id == sale_id

    def test_reprint_with_no_prior_job_creates_a_fresh_routed_job(self, conn):
        branch_id = _existing_branch_id(conn)
        device = _active_device(conn, branch_id)
        _active_sale_ticket_template(conn)
        _configure_route(conn, device)
        conn.commit()
        client = SalesPrintJobClient(conn)

        job = client.try_create_or_reprint_job(
            sale_id=new_uuid(), branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=True, reprint_reason="Reimpresión")

        assert job is not None
        assert job.reprint_of_job_id is None

    def test_reprint_with_a_printed_prior_job_creates_a_linked_reprint(self, conn):
        branch_id = _existing_branch_id(conn)
        device = _active_device(conn, branch_id)
        _active_sale_ticket_template(conn)
        _configure_route(conn, device)
        conn.commit()
        client = SalesPrintJobClient(conn)
        sale_id = new_uuid()

        original = client.try_create_or_reprint_job(
            sale_id=sale_id, branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        client.mark_printed(original)

        reprint = client.try_create_or_reprint_job(
            sale_id=sale_id, branch_id=branch_id, actor_user_id="cashier-2",
            is_reprint=True, reprint_reason="Ticket dañado")

        assert reprint is not None
        assert reprint.id != original.id
        assert reprint.reprint_of_job_id == original.id
        assert reprint.reprint_reason == "Ticket dañado"

    def test_reprint_with_prior_job_still_in_flight_is_skipped_not_faked(self, conn):
        """A prior job that hasn't reached a terminal state yet must never
        be silently replaced by an unrelated fresh routed job — that would
        misrepresent the audit trail. This is a governance skip (`None`),
        not a fallback."""
        branch_id = _existing_branch_id(conn)
        device = _active_device(conn, branch_id)
        _active_sale_ticket_template(conn)
        _configure_route(conn, device)
        conn.commit()
        client = SalesPrintJobClient(conn)
        sale_id = new_uuid()

        original = client.try_create_or_reprint_job(
            sale_id=sale_id, branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        assert original.status is PrintJobStatus.PRINTING  # still in flight, not PRINTED/FAILED

        result = client.try_create_or_reprint_job(
            sale_id=sale_id, branch_id=branch_id, actor_user_id="cashier-2",
            is_reprint=True, reprint_reason="Reimpresión")

        assert result is None

    def test_mark_printed_and_mark_failed_persist(self, conn):
        branch_id = _existing_branch_id(conn)
        device = _active_device(conn, branch_id)
        _active_sale_ticket_template(conn)
        _configure_route(conn, device)
        conn.commit()
        client = SalesPrintJobClient(conn)

        job = client.try_create_or_reprint_job(
            sale_id=new_uuid(), branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        client.mark_printed(job)
        assert job.status is PrintJobStatus.PRINTED

        job2 = client.try_create_or_reprint_job(
            sale_id=new_uuid(), branch_id=branch_id, actor_user_id="cashier-1",
            is_reprint=False, reprint_reason="")
        client.mark_failed(job2, "Impresora sin papel")
        assert job2.status is PrintJobStatus.FAILED
        assert job2.failure_reason == "Impresora sin papel"
