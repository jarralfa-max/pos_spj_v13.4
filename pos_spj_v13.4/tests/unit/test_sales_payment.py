"""SALES-13/POS-13 — Pago: Cash, Card, Transfer, Mixed, Credit, Mercado
Pago, Tests.

Credit tests build the REAL `cuentas_por_cobrar` schema (exact DDL from
`migrations/m000_base_schema.py`, including its `idx_cxc_venta_unica`
partial unique index) plus a minimal `clientes` row shaped exactly like
`CustomerCreditService.get_customer()` reads it — same "copy the real DDL,
don't approximate" discipline as every prior phase's hand-rolled fixtures.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.permissions import SalesPermissions
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    StartSaleUseCase,
)
from backend.application.sales.use_cases.customer_use_cases import QuickCreateCustomerForSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import (
    CompleteSaleUseCase,
    RecordSalePaymentUseCase,
)
from backend.domain.sales.entities import Sale
from backend.domain.sales.enums import PaymentMethod, SaleStatus
from backend.domain.sales.exceptions import (
    SaleInvalidStateError,
    SalePaymentIncompleteError,
)
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


def _allow_all_sales() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _allow_all_customers() -> CustomerAuthorizationPolicy:
    return CustomerAuthorizationPolicy.permissive_for_tests()


# ── Domain: Sale.record_payment / complete ──────────────────────────────

class TestSalePaymentDomain:
    def _sale_ready_for_checkout(self, total="100.00"):
        sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
        sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")),
                      unit_price=Decimal(total))
        sale.begin_checkout()
        return sale

    def test_record_payment_requires_checkout_or_payment_pending_status(self):
        from backend.domain.sales.entities import Sale

        sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
        with pytest.raises(SaleInvalidStateError):
            sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("10"),
                                captured_by_user_id=new_uuid())

    def test_complete_requires_full_payment(self):
        sale = self._sale_ready_for_checkout(total="100.00")
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("40.00"),
                            captured_by_user_id=new_uuid())
        with pytest.raises(SalePaymentIncompleteError):
            sale.complete()

    def test_complete_succeeds_once_fully_paid(self):
        sale = self._sale_ready_for_checkout(total="100.00")
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("100.00"),
                            captured_by_user_id=new_uuid())
        sale.complete()
        assert sale.status is SaleStatus.COMPLETED
        assert sale.completed_at is not None

    def test_overpayment_is_allowed_change_scenario(self):
        sale = self._sale_ready_for_checkout(total="100.00")
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("150.00"),
                            captured_by_user_id=new_uuid())
        sale.complete()
        assert sale.status is SaleStatus.COMPLETED

    def test_mixed_payment_detected_only_with_two_distinct_methods(self):
        sale = self._sale_ready_for_checkout(total="100.00")
        sale.record_payment(method=PaymentMethod.CASH, amount=Decimal("50.00"),
                            captured_by_user_id=new_uuid())
        assert sale.is_mixed_payment is False
        sale.record_payment(method=PaymentMethod.CARD, amount=Decimal("50.00"),
                            captured_by_user_id=new_uuid())
        assert sale.is_mixed_payment is True
        assert sale.total_paid == Decimal("100.00")


# ── Application use cases ────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_customers_crm_schema(c)
    c.execute("""
        CREATE TABLE clientes (
            id TEXT PRIMARY KEY, nombre TEXT NOT NULL, telefono TEXT, email TEXT,
            activo INTEGER DEFAULT 1,
            allows_credit INTEGER DEFAULT 0, credit_limit REAL DEFAULT 0,
            credit_balance REAL DEFAULT 0, saldo REAL DEFAULT 0, puntos INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE cuentas_por_cobrar (
            id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT NOT NULL, venta_id TEXT,
            folio TEXT, monto_original REAL NOT NULL, saldo_pendiente REAL NOT NULL,
            estado TEXT DEFAULT 'pendiente', sucursal_id TEXT,
            fecha DATETIME DEFAULT (datetime('now')), fecha_pago DATETIME
        )
    """)
    c.execute("""
        CREATE UNIQUE INDEX idx_cxc_venta_unica
            ON cuentas_por_cobrar(venta_id) WHERE venta_id IS NOT NULL
    """)
    c.commit()
    yield c
    c.close()


def _sale_ready_for_checkout(conn, *, price="100.00") -> tuple[str, str, str]:
    branch, cashier = new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(_allow_all_sales()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    BeginSaleCheckoutUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    return sale_id, cashier, branch


def _create_customer(conn, *, display_name="Ana Torres") -> str:
    return QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
        display_name=display_name).entity_id


class TestRecordSalePaymentUseCase:
    def test_records_cash_payment(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        result = RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CASH", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert len(sale.payments) == 1
        assert sale.payments[0].method is PaymentMethod.CASH

    def test_unknown_method_fails_validation(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        result = RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="BITCOIN", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "VALIDATION"

    def test_second_distinct_method_requires_mixed_permission(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)

        class _AllowExceptMixed:
            def has_permission(self, user_id, permission_code):
                return permission_code != SalesPermissions.PAYMENT_MIXED

        auth = SalesAuthorizationPolicy(_AllowExceptMixed())
        RecordSalePaymentUseCase(auth).execute(
            conn, sale_id=sale_id, method="CASH", amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        result = RecordSalePaymentUseCase(auth).execute(
            conn, sale_id=sale_id, method="CARD", amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_credit_without_assigned_customer_is_rejected(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        result = RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CREDIT", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "CREDIT_NOT_AUTHORIZED"

    def test_credit_denied_when_customer_has_no_credit_authorized(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        customer_id = _create_customer(conn)
        AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        conn.execute("INSERT OR IGNORE INTO clientes (id, nombre, allows_credit) "
                     "VALUES (?, 'Bridge stub', 0)", (legacy_id,))
        conn.commit()

        result = RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CREDIT", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "CREDIT_NOT_AUTHORIZED"

    def test_credit_approved_records_payment_and_registers_cxc(self, conn):
        sale_id, cashier, branch = _sale_ready_for_checkout(conn)
        customer_id = _create_customer(conn)
        AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        conn.execute(
            "UPDATE clientes SET allows_credit=1, credit_limit=500, credit_balance=0 WHERE id=?",
            (legacy_id,))
        conn.commit()

        result = RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CREDIT", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        cxc = conn.execute(
            "SELECT cliente_id, monto_original FROM cuentas_por_cobrar WHERE venta_id=?",
            (sale_id,)).fetchone()
        assert cxc is not None
        assert cxc["cliente_id"] == legacy_id
        assert cxc["monto_original"] == 100.0


class TestCompleteSaleUseCase:
    def test_fails_when_not_fully_paid(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CASH", amount=Decimal("40.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        result = CompleteSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PAYMENT_INCOMPLETE"

    def test_completes_once_fully_paid_and_emits_events(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CASH", amount=Decimal("60.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="CARD", amount=Decimal("40.00"),
            actor_user_id=cashier, operation_id=new_uuid())
        result = CompleteSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True

        sale = SaleRepository(conn).get(sale_id)
        assert sale.status is SaleStatus.COMPLETED
        assert sale.is_mixed_payment is True

        events = {row["event_name"] for row in conn.execute(
            "SELECT event_name FROM sales_outbox WHERE payload_json LIKE ?",
            (f'%"entity_id": "{sale_id}"%',)).fetchall()}
        assert "SALE_PAYMENT_RECORDED" in events
        assert "SALE_PAYMENT_CONFIRMED" in events
        assert "SALE_COMPLETED" in events

    def test_mercado_pago_recorded_as_a_reference_only_payment_line(self, conn):
        sale_id, cashier, _branch = _sale_ready_for_checkout(conn)
        result = RecordSalePaymentUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, method="MERCADO_PAGO", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid(), reference="mp-payment-123")
        assert result.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert sale.payments[0].reference == "mp-payment-123"
        CompleteSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert SaleRepository(conn).get(sale_id).status is SaleStatus.COMPLETED
