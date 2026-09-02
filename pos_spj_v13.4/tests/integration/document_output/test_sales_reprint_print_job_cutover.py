"""SET-12 cutover — `ReprintReceiptUseCase` wired to `SalesPrintJobClient`,
against a real (in-memory) SQLite schema combining Sales with the
born-clean Document Output/Device Management schema. Two properties under
test:

1. The real reprint (via the legacy `PrinterService` contract) must
   always succeed regardless of Document Output's configuration state —
   unconfigured, misconfigured, or even raising unexpectedly.
2. When a `SALE_TICKET` template + route ARE configured, a real
   `print_jobs` row is created, routed to the resolved device, and
   reaches a terminal state (`PRINTED`/`FAILED`) reflecting the real
   `PrinterService` outcome via the `on_success`/`on_error` callbacks.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.sales.authorization import AllowAllSalesPermissionCheckerForTests, SalesAuthorizationPolicy
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.receipt_use_cases import ReprintReceiptUseCase
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
from backend.infrastructure.db.repositories.document_output.print_job_repository import SqlitePrintJobRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


class _FakePrinterService:
    """Unlike `tests/unit/test_sales_receipts.py`'s own fake, this one
    actually invokes `on_success`/`on_error` — required to exercise the
    PrintJob terminal-state callbacks, matching the real
    `PrinterService.print_ticket()` contract."""

    def __init__(self, *, should_fail: bool = False, error_message: str = "Impresora sin papel") -> None:
        self.should_fail = should_fail
        self.error_message = error_message
        self.last_ticket_data = None

    def print_ticket(self, ticket_data, on_success=None, on_error=None) -> str:
        self.last_ticket_data = ticket_data
        if self.should_fail:
            if on_error:
                on_error(Exception(self.error_message))
        elif on_success:
            on_success()
        return "job-42"


class _RaisingSalesPrintJobClient:
    """Simulates an unexpected failure inside the Document Output
    integration itself — must never surface as a reprint failure."""

    def __init__(self, connection) -> None:
        pass

    def try_create_or_reprint_job(self, **kwargs):
        raise RuntimeError("boom: unexpected Document Output failure")


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


def _completed_sale(conn, *, price="100.00", branch: str | None = None) -> tuple[str, str, str]:
    branch = branch or new_uuid()
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid(),
        product_snapshot={"name": "Bistec"})
    BeginSaleCheckoutUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    RecordSalePaymentUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, method="CASH", amount=Decimal(price),
        actor_user_id=cashier, operation_id=new_uuid())
    result = CheckoutSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id, cashier, branch


def _active_device(conn, branch_id) -> Device:
    profile = DeviceProfile.create(
        name="Impresora térmica", device_type=DeviceType.THERMAL_PRINTER,
        connection_profile=ConnectionProfile.create(ConnectionType.USB),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=f"PRN-{new_uuid()}", name="Impresora")
    SqliteDeviceRepository(conn).save(device)
    return device


def _configure_sale_ticket_template_and_route(conn, device) -> None:
    template = DocumentTemplate.create(
        document_type=DocumentType.SALE_TICKET, name="Ticket de venta", module="sales")
    SqliteDocumentTemplateRepository(conn).save(template)
    version = DocumentTemplateVersion.create(
        template_id=template.id, content_format=RenderFormat.ESC_POS, content="<ticket/>")
    version.submit_for_approval()
    version.approve(approved_by_user_id="admin-1")
    version.activate(activated_by_user_id="admin-1")
    SqliteDocumentTemplateVersionRepository(conn).save(version)
    route = PrintRoute.create(document_type="SALE_TICKET", primary_device_id=device.id)
    SqlitePrintRouteRepository(conn).save(route)


class TestReprintAlwaysSucceedsRegardlessOfDocumentOutputState:
    def test_unconfigured_document_output_does_not_affect_a_real_reprint(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert result.data["job_id"] == "job-42"
        assert SqlitePrintJobRepository(conn).list_by_source("sales", sale_id) == []

    def test_document_output_raising_unexpectedly_does_not_break_a_real_reprint(self, conn, monkeypatch):
        sale_id, cashier, _branch = _completed_sale(conn)
        printer = _FakePrinterService()
        monkeypatch.setattr(
            "backend.application.sales.use_cases.receipt_use_cases.SalesPrintJobClient",
            _RaisingSalesPrintJobClient)

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert result.data["job_id"] == "job-42"


class TestReprintWithDocumentOutputConfigured:
    def test_reprint_creates_a_real_print_job_reaching_printed(self, conn):
        branch = _existing_branch_id(conn)
        sale_id, cashier, _branch = _completed_sale(conn, branch=branch)
        device = _active_device(conn, branch)
        _configure_sale_ticket_template_and_route(conn, device)
        conn.commit()
        printer = _FakePrinterService(should_fail=False)

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        jobs = SqlitePrintJobRepository(conn).list_by_source("sales", sale_id)
        assert len(jobs) == 1
        assert jobs[0].status is PrintJobStatus.PRINTED
        assert jobs[0].printer_device_id == device.id

    def test_reprint_marks_the_print_job_failed_on_printer_error(self, conn):
        branch = _existing_branch_id(conn)
        sale_id, cashier, _branch = _completed_sale(conn, branch=branch)
        device = _active_device(conn, branch)
        _configure_sale_ticket_template_and_route(conn, device)
        conn.commit()
        printer = _FakePrinterService(should_fail=True, error_message="Sin papel")

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True  # the reprint request itself still succeeds
        jobs = SqlitePrintJobRepository(conn).list_by_source("sales", sale_id)
        assert len(jobs) == 1
        assert jobs[0].status is PrintJobStatus.FAILED
        assert jobs[0].failure_reason == "Sin papel"

    def test_second_reprint_creates_a_linked_job(self, conn):
        branch = _existing_branch_id(conn)
        sale_id, cashier, _branch = _completed_sale(conn, branch=branch)
        device = _active_device(conn, branch)
        _configure_sale_ticket_template_and_route(conn, device)
        conn.commit()

        ReprintReceiptUseCase(_allow_all()).execute(
            conn, _FakePrinterService(), sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())
        ReprintReceiptUseCase(_allow_all()).execute(
            conn, _FakePrinterService(), sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid(), reason="Se manchó el ticket")

        jobs = SqlitePrintJobRepository(conn).list_by_source("sales", sale_id)
        assert len(jobs) == 2
        newest, oldest = jobs
        assert newest.reprint_of_job_id == oldest.id
        assert newest.reprint_reason == "Se manchó el ticket"
