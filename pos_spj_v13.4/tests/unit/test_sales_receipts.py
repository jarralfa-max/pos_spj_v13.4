"""SALES-17/POS-17 — Document Output: Receipt DTO, PrintJob, Reprint, PDF,
Tests.

`print_job_log` fixture uses the exact real DDL from
`migrations/standalone/056_print_job_log.py` — same "copy the real DDL,
don't approximate" discipline as every prior phase's hand-rolled fixtures.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.dto import SaleDTO
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.receipt_use_cases import (
    ReprintReceiptUseCase,
    SaveReceiptDocumentUseCase,
)
from backend.domain.sales.exceptions import SalesPermissionDeniedError
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_receipt_client import SalesReceiptClient
from backend.shared.ids import new_uuid


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


class _FakePrinterService:
    def __init__(self) -> None:
        self.last_ticket_data = None

    def print_ticket(self, ticket_data, on_success=None, on_error=None) -> str:
        self.last_ticket_data = ticket_data
        return "job-42"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    c.execute("""
        CREATE TABLE print_job_log (
            id TEXT NOT NULL PRIMARY KEY, job_id TEXT NOT NULL, job_type TEXT NOT NULL DEFAULT 'ticket',
            plantilla TEXT DEFAULT '', impresora TEXT DEFAULT '', folio TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'queued', reintentos INTEGER DEFAULT 0,
            total REAL DEFAULT 0, sucursal_id TEXT, usuario TEXT DEFAULT '',
            error_msg TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT
        )
    """)
    c.commit()
    yield c
    c.close()


def _completed_sale(conn, *, price="100.00", method="CASH", second_method=None, second_amount=None):
    branch, cashier = new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid(),
        product_snapshot={"name": "Bistec"})
    BeginSaleCheckoutUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    sale = SaleRepository(conn).get(sale_id)
    pay_amount = sale.totals.total - (second_amount or Decimal("0"))
    RecordSalePaymentUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, method=method, amount=pay_amount,
        actor_user_id=cashier, operation_id=new_uuid())
    if second_method:
        RecordSalePaymentUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, method=second_method, amount=second_amount,
            actor_user_id=cashier, operation_id=new_uuid())
    result = CheckoutSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id, cashier, branch


class TestBuildReceiptDataFromSale:
    def test_derives_cash_payment_with_no_change(self, conn):
        sale_id, _cashier, _branch = _completed_sale(conn, price="100.00")
        sale_dto = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))
        receipt = SalesReceiptClient.build_receipt_data_from_sale(sale_dto, cajero_nombre="Ana")
        assert receipt.forma_pago == "CASH"
        assert receipt.efectivo_recibido == Decimal("100.00")
        assert receipt.cambio == Decimal("0")
        assert receipt.lines[0].name == "Bistec"

    def test_derives_mixed_payment_label(self, conn):
        sale_id, _cashier, _branch = _completed_sale(
            conn, price="100.00", method="CASH", second_method="CARD", second_amount=Decimal("40.00"))
        sale_dto = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))
        receipt = SalesReceiptClient.build_receipt_data_from_sale(sale_dto, cajero_nombre="Ana")
        assert receipt.forma_pago == "Mixto"
        assert receipt.efectivo_recibido == Decimal("60.00")

    def test_card_only_payment_has_no_efectivo(self, conn):
        sale_id, _cashier, _branch = _completed_sale(conn, price="100.00", method="CARD")
        sale_dto = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))
        receipt = SalesReceiptClient.build_receipt_data_from_sale(sale_dto, cajero_nombre="Ana")
        assert receipt.forma_pago == "CARD"
        assert receipt.efectivo_recibido == Decimal("0")
        assert receipt.cambio == Decimal("0")


class TestPrintJobStatus:
    def test_returns_none_when_job_not_logged(self, conn):
        client = SalesReceiptClient(_FakePrinterService(), conn)
        assert client.get_job_status("nope") is None

    def test_returns_real_row_from_print_job_log(self, conn):
        conn.execute(
            "INSERT INTO print_job_log (id, job_id, folio, estado, reintentos, error_msg, finished_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (new_uuid(), "job-42", "F-001", "success", 1, "", "2026-08-17T12:00:00+00:00"))
        conn.commit()
        client = SalesReceiptClient(_FakePrinterService(), conn)
        status = client.get_job_status("job-42")
        assert status is not None
        assert status.status == "success"
        assert status.folio == "F-001"

    def test_get_job_status_requires_a_connection(self):
        client = SalesReceiptClient(_FakePrinterService())
        with pytest.raises(RuntimeError):
            client.get_job_status("job-42")


class TestReprintReceiptUseCase:
    def test_requires_reprint_permission(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        denied = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        result = ReprintReceiptUseCase(denied).execute(
            conn, _FakePrinterService(), sale_id=sale_id, cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_fails_for_a_sale_that_never_completed(self, conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, _FakePrinterService(), sale_id=sale_id, cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "RECEIPT_NOT_AVAILABLE"

    def test_reprints_and_derives_original_payment(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn, price="75.00")
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert printer.last_ticket_data["pago"]["forma_pago"] == "CASH"
        assert printer.last_ticket_data["totales"]["total_final"] == 75.0
        assert result.data["job_id"] == "job-42"

    def test_reprint_emits_event_to_outbox(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        ReprintReceiptUseCase(_allow_all()).execute(
            conn, _FakePrinterService(), sale_id=sale_id, cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())
        event = conn.execute(
            "SELECT event_name FROM sales_outbox WHERE event_name='SALE_RECEIPT_REPRINT_REQUESTED'"
            " AND payload_json LIKE ?", (f'%"entity_id": "{sale_id}"%',)).fetchone()
        assert event is not None


class TestSaveReceiptDocumentUseCase:
    def test_requires_view_permission(self, conn, tmp_path):
        sale_id, cashier, _branch = _completed_sale(conn)
        denied = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        result = SaveReceiptDocumentUseCase(denied).execute(
            conn, sale_id=sale_id, filepath=str(tmp_path / "t.pdf"), cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_saves_a_real_document_using_the_real_default_template(self, conn, tmp_path):
        """No `ticket_template_html` configured — must render through the
        SAME default template `SalesService._default_ticket_template()`
        falls back to in production, not an invented format."""
        sale_id, cashier, _branch = _completed_sale(conn, price="88.00")
        filepath = str(tmp_path / "ticket.pdf")

        result = SaveReceiptDocumentUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, filepath=filepath, cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is True
        assert result.data["filepath"] == filepath
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "Bistec" in content
        assert "$88.00" in content
        assert "Ana" in content  # {{cajero}}

    def test_honors_a_configured_custom_template(self, conn, tmp_path):
        conn.execute(
            "INSERT INTO configuraciones (clave, valor) VALUES "
            "('ticket_template_html', '<div>PLANTILLA PERSONALIZADA {{folio}} {{total}}</div>')")
        conn.commit()
        sale_id, cashier, _branch = _completed_sale(conn, price="50.00")
        filepath = str(tmp_path / "ticket.pdf")

        SaveReceiptDocumentUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, filepath=filepath, cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())

        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        assert "PLANTILLA PERSONALIZADA" in content
        assert "$50.00" in content

    def test_fails_for_uncompleted_sale(self, conn, tmp_path):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        result = SaveReceiptDocumentUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, filepath=str(tmp_path / "t.pdf"), cajero_nombre="Ana",
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "RECEIPT_NOT_AVAILABLE"
