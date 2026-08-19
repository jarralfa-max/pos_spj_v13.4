"""SALES-12/POS-12 — Hardware: Scanner, Printer, Scale, Terminal, Drawer,
Customer display, Tests.

Cash-register-backed clients (drawer, terminal) build the REAL Caja
bounded-context schema (`migrations.standalone.
175_cash_register_bounded_context_schema`) and inject fake gateway doubles
exactly the way `tests/integration/cash_register/
test_cash_hardware_operations.py` already does — proving Sales composes
correctly into Caja's real, audited use cases without duplicating Caja's
own driver tests. Scale/printer clients wrap legacy services this
repository doesn't own the internals of (`HardwareService`, `PrinterService`)
with fake doubles for the same reason: this phase tests what
`backend/infrastructure/integrations/sales_*` actually owns (the
translation contract), not code already real and tested elsewhere.
"""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.hardware import CashHardwareError, TerminalPaymentResult
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.dto import SaleDTO
from backend.application.sales.queries.customer_display_query_service import CustomerDisplayQueryService
from backend.application.sales.queries.device_health_query_service import DeviceHealthQueryService
from backend.application.sales.queries.sale_query_service import SaleQueryService
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.scan_use_cases import ScanCodeRouter
from backend.domain.inventory.exceptions import InvalidCatchWeightError
from backend.domain.sales.enums import PaymentMethod, ScanContext
from backend.domain.sales.exceptions import SalesPermissionDeniedError
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.integrations.sales_cash_drawer_client import SalesCashDrawerGateway
from backend.infrastructure.integrations.sales_payment_terminal_client import SalesPaymentTerminalClient
from backend.infrastructure.integrations.sales_receipt_client import SalesReceiptClient
from backend.infrastructure.integrations.sales_scale_client import SalesScaleGateway
from backend.shared.ids import new_uuid


def _allow_all_sales() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


# ── Scale ────────────────────────────────────────────────────────────────

class _FakeHardwareService:
    def __init__(self, weight: float) -> None:
        self._weight = weight

    def read_scale(self) -> float:
        return self._weight


class TestSalesScaleGateway:
    def test_read_translates_weight_into_reading(self):
        gateway = SalesScaleGateway(_FakeHardwareService(1.250), device_id="bascula-1")
        reading = gateway.read()
        assert reading.gross == Decimal("1.250")
        assert reading.stable is True
        assert reading.source.value == "SCALE"

    def test_read_raises_on_no_reading(self):
        gateway = SalesScaleGateway(_FakeHardwareService(0.0))
        with pytest.raises(InvalidCatchWeightError):
            gateway.read()


# ── Printer / Receipt ───────────────────────────────────────────────────

class _FakePrinterService:
    def __init__(self) -> None:
        self.last_ticket_data = None

    def print_ticket(self, ticket_data, on_success=None, on_error=None) -> str:
        self.last_ticket_data = ticket_data
        return "job-1"


def _sale_dto_with_line() -> SaleDTO:
    conn = sqlite3.connect(":memory:")
    create_sales_schema(conn)
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_allow_all_sales()).execute(
        conn, branch_id=new_uuid(), cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("2"),
        unit_price=Decimal("50.00"), actor_user_id=cashier, operation_id=new_uuid(),
        product_snapshot={"name": "Bistec"})
    sale = SaleRepository(conn).get(sale_id)
    conn.close()
    return SaleDTO.from_entity(sale)


class TestSalesReceiptClient:
    def test_print_receipt_shapes_ticket_payload_from_sale_dto(self):
        sale = _sale_dto_with_line()
        printer = _FakePrinterService()
        client = SalesReceiptClient(printer)

        job_id = client.print_receipt(
            sale, forma_pago="Efectivo", cajero_nombre="Ana",
            efectivo_recibido=Decimal("200.00"))

        assert job_id == "job-1"
        data = printer.last_ticket_data
        assert data["venta_id"] == sale.id
        assert data["cajero"] == "Ana"
        assert data["cliente"] == "Público General"
        assert data["items"] == [
            {"nombre": "Bistec", "unidad": "PZA", "cantidad": 2.0,
             "precio_unitario": 50.0, "total": 100.0}
        ]
        assert data["totales"]["total_final"] == float(sale.total)
        assert data["pago"]["forma_pago"] == "Efectivo"
        assert data["pago"]["cambio"] == pytest.approx(200.0 - float(sale.total))


# ── Cash drawer / payment terminal (real Caja bounded context) ─────────

class _Allow:
    def has_permission(self, user_id, permission_code): return True
    def can_access_branch(self, *, user_id, branch_id): return True


class _FakeDrawer:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open_drawer(self, drawer_id: str) -> None:
        self.opened.append(drawer_id)


class _FakeTerminal:
    def __init__(self, *, approved: bool = True) -> None:
        self._approved = approved
        self.charged: list[tuple] = []

    def charge(self, terminal_id, request):
        self.charged.append((terminal_id, request))
        return TerminalPaymentResult(approved=self._approved, transaction_id="tx-1",
                                     authorization_code="AUTH1")


@pytest.fixture
def cash_conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema"
    ).run(c)
    yield c
    c.close()


def _seed_cash_devices(conn):
    branch, register = new_uuid(), new_uuid()
    drawer, terminal = new_uuid(), new_uuid()
    now = "2026-08-17T12:00:00+00:00"
    conn.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
                 (register, branch, "Caja 1", "ACTIVE", None, now, now))
    conn.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
                 (drawer, branch, register, "Cajón 1", "ACTIVE", now, now))
    conn.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
                 (terminal, branch, register, "Terminal 1", "ACTIVE", now, now))
    conn.commit()
    return branch, drawer, terminal


class TestSalesCashDrawerGateway:
    def test_open_delegates_to_real_caja_use_case_and_is_audited(self, cash_conn):
        branch, drawer, _terminal = _seed_cash_devices(cash_conn)
        fake_drawer, actor, operation = _FakeDrawer(), new_uuid(), new_uuid()
        authorization = CashAuthorizationPolicy(_Allow(), _Allow())
        gateway = SalesCashDrawerGateway(authorization, fake_drawer)
        sale_id = new_uuid()

        gateway.open(cash_conn, drawer_id=drawer, branch_id=branch, actor_user_id=actor,
                     operation_id=operation, sale_id=sale_id)

        assert fake_drawer.opened == [drawer]
        audit = cash_conn.execute(
            "SELECT action FROM cash_audit_log WHERE operation_id=?", (operation,)).fetchone()
        assert audit == ("CASH_DRAWER_OPENED",)


class TestSalesPaymentTerminalClient:
    def test_charge_delegates_and_returns_real_result(self, cash_conn):
        branch, _drawer, terminal = _seed_cash_devices(cash_conn)
        fake_terminal, actor, operation = _FakeTerminal(), new_uuid(), new_uuid()
        authorization = CashAuthorizationPolicy(_Allow(), _Allow())
        client = SalesPaymentTerminalClient(authorization, fake_terminal)

        result = client.charge(
            cash_conn, terminal_id=terminal, amount=Decimal("150.00"), currency="mxn",
            reference="venta-1", branch_id=branch, actor_user_id=actor, operation_id=operation)

        assert result.approved is True
        assert result.transaction_id == "tx-1"
        assert fake_terminal.charged[0][1].currency == "MXN"

    def test_declined_charge_is_still_a_success_from_the_hardware_boundary(self, cash_conn):
        branch, _drawer, terminal = _seed_cash_devices(cash_conn)
        authorization = CashAuthorizationPolicy(_Allow(), _Allow())
        client = SalesPaymentTerminalClient(authorization, _FakeTerminal(approved=False))

        result = client.charge(
            cash_conn, terminal_id=terminal, amount=Decimal("10.00"), currency="MXN",
            reference="venta-2", branch_id=branch, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        assert result.approved is False

    def test_driver_failure_raises_cash_hardware_error(self, cash_conn):
        branch, _drawer, terminal = _seed_cash_devices(cash_conn)

        class _Broken:
            def charge(self, terminal_id, request):
                raise OSError("vendor detail must not leak")

        authorization = CashAuthorizationPolicy(_Allow(), _Allow())
        client = SalesPaymentTerminalClient(authorization, _Broken())
        with pytest.raises(CashHardwareError):
            client.charge(
                cash_conn, terminal_id=terminal, amount=Decimal("10.00"), currency="MXN",
                reference="venta-3", branch_id=branch, actor_user_id=new_uuid(),
                operation_id=new_uuid())


# ── Scanner ──────────────────────────────────────────────────────────────

@pytest.fixture
def scan_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    create_customers_crm_schema(c)
    c.execute("""
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, email TEXT,
            codigo_qr TEXT, codigo_fidelidad TEXT, activo INTEGER DEFAULT 1, puntos INTEGER DEFAULT 0
        )
    """)
    base_list_id = new_uuid()
    c.execute(
        "INSERT INTO price_list (id, code, name, kind, status, discount_pct) "
        "VALUES (?, 'BASE', 'Lista base', 'BASE', 'ACTIVE', '0')", (base_list_id,))
    c.commit()
    yield c
    c.close()


def _add_scannable_product(conn, *, branch_id, barcode, price="45.00") -> str:
    product_id = new_uuid()
    conn.execute(
        "INSERT INTO products (id, code, name, product_type, base_unit_id, lifecycle_status) "
        "VALUES (?,?,?,?,?,?)", (product_id, "SKU-1", "Bistec", "SIMPLE", "PZA", "ACTIVE"))
    base_list_id = conn.execute("SELECT id FROM price_list WHERE code='BASE'").fetchone()["id"]
    conn.execute(
        "INSERT INTO product_price (id, price_list_id, product_id, sale_price, branch_id) "
        "VALUES (?,?,?,?,'')", (new_uuid(), base_list_id, product_id, price))
    conn.execute(
        "INSERT INTO product_barcodes (id, product_id, barcode_value, barcode_type, is_primary) "
        "VALUES (?,?,?,'EAN13',1)", (new_uuid(), product_id, barcode))
    conn.commit()
    return product_id


def _start_sale(conn, *, branch_id) -> tuple[str, str]:
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_allow_all_sales()).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    return sale_id, cashier


class TestScanCodeRouter:
    def test_product_context_resolves_barcode_and_adds_line(self, scan_conn):
        branch = new_uuid()
        product_id = _add_scannable_product(scan_conn, branch_id=branch, barcode="750123")
        sale_id, cashier = _start_sale(scan_conn, branch_id=branch)
        router = ScanCodeRouter(_allow_all_sales())

        result = router.route(
            scan_conn, sale_id=sale_id, code="750123", context=ScanContext.PRODUCT,
            branch_id=branch, actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is True
        sale = SaleRepository(scan_conn).get(sale_id)
        assert len(sale.lines) == 1
        assert sale.lines[0].product_id == product_id

    def test_auto_context_falls_back_to_customer_card_when_no_product_matches(self, scan_conn):
        branch = new_uuid()
        sale_id, cashier = _start_sale(scan_conn, branch_id=branch)
        scan_conn.execute(
            "INSERT INTO clientes (id, nombre, codigo_fidelidad) VALUES (?, 'Ana', 'CARD-9')",
            (new_uuid(),))
        scan_conn.commit()
        router = ScanCodeRouter(_allow_all_sales())

        result = router.route(
            scan_conn, sale_id=sale_id, code="CARD-9", context=ScanContext.AUTO,
            branch_id=branch, actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is True
        sale = SaleRepository(scan_conn).get(sale_id)
        assert sale.customer_id is not None

    def test_product_context_with_unknown_code_fails_explicitly(self, scan_conn):
        branch = new_uuid()
        sale_id, cashier = _start_sale(scan_conn, branch_id=branch)
        router = ScanCodeRouter(_allow_all_sales())

        result = router.route(
            scan_conn, sale_id=sale_id, code="no-such-code", context=ScanContext.PRODUCT,
            branch_id=branch, actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is False
        assert result.error_code == "SCAN_CODE_NOT_RESOLVED"

    def test_empty_code_fails_explicitly(self, scan_conn):
        branch = new_uuid()
        sale_id, cashier = _start_sale(scan_conn, branch_id=branch)
        router = ScanCodeRouter(_allow_all_sales())

        result = router.route(
            scan_conn, sale_id=sale_id, code="   ", context=ScanContext.AUTO,
            branch_id=branch, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "SCAN_CODE_NOT_RESOLVED"


# ── Customer display ─────────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_customers_crm_schema(c)
    c.commit()
    yield c
    c.close()


class TestCustomerDisplayQueryService:
    def test_active_sale_shows_cart_screen_with_lines(self, conn):
        branch = new_uuid()
        sale_id, cashier = _start_sale(conn, branch_id=branch)
        AddSaleLineUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("30.00"), actor_user_id=cashier, operation_id=new_uuid(),
            product_snapshot={"name": "Chorizo"})

        service = CustomerDisplayQueryService(conn, _allow_all_sales())
        state = service.current_state(sale_id, requester_user_id=cashier)

        assert state.screen == "CART"
        assert state.lines[0].name == "Chorizo"
        assert state.total == Decimal("30.00")
        assert state.customer_name is None

    def test_completed_sale_shows_thank_you_screen(self, conn):
        branch = new_uuid()
        sale_id, cashier = _start_sale(conn, branch_id=branch)
        AddSaleLineUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("10.00"), actor_user_id=cashier, operation_id=new_uuid())
        sale = SaleRepository(conn).get(sale_id)
        sale.begin_checkout()
        sale.mark_payment_pending()
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("10.00"),
                            captured_by_user_id=cashier)
        sale.complete()
        SaleRepository(conn).save(sale)

        service = CustomerDisplayQueryService(conn, _allow_all_sales())
        state = service.current_state(sale_id, requester_user_id=cashier)
        assert state.screen == "THANK_YOU"
        assert state.message


# ── Device health ─────────────────────────────────────────────────────────

@pytest.fixture
def hw_conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    # Exact DDL from migrations/m050_hardware_config_canonical.py — copied,
    # not approximated, same discipline as SALES-11's hand-rolled loyalty_ledger.
    c.execute("""
        CREATE TABLE hardware_config (
            tipo TEXT NOT NULL PRIMARY KEY, nombre TEXT NOT NULL, driver TEXT,
            puerto TEXT, configuraciones TEXT, activo INTEGER DEFAULT 1,
            sucursal_id TEXT, fecha_actualizacion DATETIME DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    yield c
    c.close()


class TestDeviceHealthQueryService:
    def test_configured_device_reports_true(self, hw_conn):
        hw_conn.execute(
            "INSERT INTO hardware_config (tipo, nombre, puerto, activo) "
            "VALUES ('bascula', 'Báscula', 'COM3', 1)")
        hw_conn.commit()
        service = DeviceHealthQueryService(hw_conn, _allow_all_sales())
        results = {d.device_type: d for d in service.check_all(requester_user_id=new_uuid())}
        assert results["bascula"].configured is True

    def test_missing_row_reports_unconfigured(self, hw_conn):
        service = DeviceHealthQueryService(hw_conn, _allow_all_sales())
        results = {d.device_type: d for d in service.check_all(requester_user_id=new_uuid())}
        assert results["scanner"].configured is False

    def test_unbuilt_devices_are_reported_honestly_as_unconfigured(self, hw_conn):
        service = DeviceHealthQueryService(hw_conn, _allow_all_sales())
        results = {d.device_type: d for d in service.check_all(requester_user_id=new_uuid())}
        assert results["terminal_pago"].configured is False
        assert results["customer_display"].configured is False

    def test_inactive_row_reports_false_even_with_a_port(self, hw_conn):
        hw_conn.execute(
            "INSERT INTO hardware_config (tipo, nombre, puerto, activo) "
            "VALUES ('cajon', 'Cajón', 'escpos', 0)")
        hw_conn.commit()
        service = DeviceHealthQueryService(hw_conn, _allow_all_sales())
        results = {d.device_type: d for d in service.check_all(requester_user_id=new_uuid())}
        assert results["cajon"].configured is False
        assert results["cajon"].enabled is False

    def test_requires_diagnostics_permission(self, hw_conn):
        service = DeviceHealthQueryService(
            hw_conn, SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests()))
        with pytest.raises(SalesPermissionDeniedError):
            service.check_all(requester_user_id=new_uuid())
