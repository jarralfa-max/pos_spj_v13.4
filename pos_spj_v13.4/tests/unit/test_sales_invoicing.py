"""SALES-18/POS-18 — Fiscal: Invoice request, Status, Errors, Tests.

No real PAC integration exists anywhere in this repository (confirmed by
research) — these tests exercise exactly what Sales itself owns per master
prompt §15 ("Ventas conserva snapshots históricos"): recording a request
with real fiscal data resolved from Customer Master's `CustomerTaxProfile`,
and the real REQUESTED/ISSUED/ERROR status lifecycle — never a fabricated
auto-stamping outcome.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    DenyAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    StartSaleUseCase,
)
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.customer_use_cases import QuickCreateCustomerForSaleUseCase
from backend.application.sales.use_cases.invoice_use_cases import (
    MarkInvoiceErrorUseCase,
    MarkInvoiceIssuedUseCase,
    RequestInvoiceUseCase,
)
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.domain.customers.entities.customer_tax_profile import CustomerTaxProfile
from backend.domain.sales.entities import Sale
from backend.domain.sales.enums import InvoiceStatus
from backend.domain.sales.exceptions import (
    InvoiceAlreadyPendingError,
    InvoiceRequestNotAllowedError,
    InvoiceTransitionNotAllowedError,
)
from backend.domain.sales.value_objects.quantity import Quantity
from backend.infrastructure.db.repositories.customers.customer_child_repositories import (
    CustomerTaxProfileRepository,
)
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _allow_all_customers() -> CustomerAuthorizationPolicy:
    return CustomerAuthorizationPolicy.permissive_for_tests()


# ── Domain ───────────────────────────────────────────────────────────────

def _completed_sale_entity() -> Sale:
    sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
    sale.add_line(product_id=new_uuid(), quantity=Quantity(Decimal("1")), unit_price=Decimal("100.00"))
    sale.begin_checkout()
    from backend.domain.sales.enums import PaymentMethod

    sale.record_payment(method=PaymentMethod.CASH, amount=sale.totals.total,
                        captured_by_user_id=new_uuid())
    sale.complete()
    return sale


class TestSaleInvoiceRequestDomain:
    def test_cannot_request_invoice_before_completion(self):
        sale = Sale.start(branch_id=new_uuid(), cashier_user_id=new_uuid(), operation_id=new_uuid())
        with pytest.raises(InvoiceRequestNotAllowedError):
            sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana",
                                 cfdi_use="S01", requested_by_user_id=new_uuid())

    def test_requires_a_tax_identifier(self):
        sale = _completed_sale_entity()
        with pytest.raises(InvoiceRequestNotAllowedError):
            sale.request_invoice(tax_identifier="   ", legal_name="Ana", cfdi_use="S01",
                                 requested_by_user_id=new_uuid())

    def test_cannot_request_twice_while_one_is_pending(self):
        sale = _completed_sale_entity()
        sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana", cfdi_use="S01",
                             requested_by_user_id=new_uuid())
        with pytest.raises(InvoiceAlreadyPendingError):
            sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana", cfdi_use="S01",
                                 requested_by_user_id=new_uuid())

    def test_mark_issued_transitions_and_stores_uuid(self):
        sale = _completed_sale_entity()
        request = sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana",
                                       cfdi_use="S01", requested_by_user_id=new_uuid())
        sale.mark_invoice_issued(request.id, uuid_fiscal="ABC-123")
        assert request.status is InvoiceStatus.ISSUED
        assert request.uuid_fiscal == "ABC-123"

    def test_mark_error_transitions_and_stores_message(self):
        sale = _completed_sale_entity()
        request = sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana",
                                       cfdi_use="S01", requested_by_user_id=new_uuid())
        sale.mark_invoice_error(request.id, error_message="PAC timeout")
        assert request.status is InvoiceStatus.ERROR
        assert request.error_message == "PAC timeout"

    def test_can_retry_after_an_error(self):
        sale = _completed_sale_entity()
        first = sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana",
                                     cfdi_use="S01", requested_by_user_id=new_uuid())
        sale.mark_invoice_error(first.id, error_message="PAC timeout")
        second = sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana",
                                      cfdi_use="S01", requested_by_user_id=new_uuid())
        assert second.id != first.id
        assert len(sale.invoice_requests) == 2

    def test_cannot_resolve_an_already_resolved_request(self):
        sale = _completed_sale_entity()
        request = sale.request_invoice(tax_identifier="XAXX010101000", legal_name="Ana",
                                       cfdi_use="S01", requested_by_user_id=new_uuid())
        sale.mark_invoice_issued(request.id, uuid_fiscal="ABC-123")
        with pytest.raises(InvoiceTransitionNotAllowedError):
            sale.mark_invoice_error(request.id, error_message="too late")


# ── Application use cases ────────────────────────────────────────────────

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_customers_crm_schema(c)
    c.commit()
    yield c
    c.close()


def _completed_sale(conn, *, price="100.00", customer_id=None):
    branch, cashier = new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    if customer_id:
        assign_result = AssignCustomerToSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier,
            operation_id=new_uuid())
        assert assign_result.success, assign_result.message
    BeginSaleCheckoutUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    sale = SaleRepository(conn).get(sale_id)
    RecordSalePaymentUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, method="CASH", amount=sale.totals.total,
        actor_user_id=cashier, operation_id=new_uuid())
    result = CheckoutSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id, cashier, branch


def _create_customer(conn) -> str:
    return QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
        conn, actor_user_id=new_uuid(), operation_id=new_uuid(),
        display_name="Ana Torres").entity_id


class TestRequestInvoiceUseCase:
    def test_requires_permission(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        denied = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        result = RequestInvoiceUseCase(denied).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_fails_for_a_sale_not_yet_completed(self, conn):
        branch, cashier = new_uuid(), new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "INVOICE_REQUEST_NOT_ALLOWED"

    def test_defaults_to_walk_in_rfc_without_customer_or_explicit_data(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert sale.invoice_requests[0].tax_identifier == "XAXX010101000"
        assert sale.invoice_requests[0].legal_name == "PUBLICO EN GENERAL"

    def test_resolves_real_tax_profile_from_customer_master(self, conn):
        customer_id = _create_customer(conn)
        CustomerTaxProfileRepository(conn).save(CustomerTaxProfile.create(
            customer_id=customer_id, tax_identifier="XEXX010101000", legal_name="Ana Torres SA",
            default_cfdi_use="G03"))
        conn.commit()
        sale_id, cashier, _branch = _completed_sale(conn, customer_id=customer_id)

        result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is True
        request = SaleRepository(conn).get(sale_id).invoice_requests[0]
        assert request.tax_identifier == "XEXX010101000"
        assert request.legal_name == "Ana Torres SA"
        assert request.cfdi_use == "G03"

    def test_explicit_arguments_win_over_customer_profile(self, conn):
        customer_id = _create_customer(conn)
        CustomerTaxProfileRepository(conn).save(CustomerTaxProfile.create(
            customer_id=customer_id, tax_identifier="XEXX010101000", legal_name="Ana Torres SA"))
        conn.commit()
        sale_id, cashier, _branch = _completed_sale(conn, customer_id=customer_id)

        result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid(),
            tax_identifier="OTRO010101ABC", legal_name="Otro Nombre")

        assert result.success is True
        request = SaleRepository(conn).get(sale_id).invoice_requests[0]
        assert request.tax_identifier == "OTRO010101ABC"
        assert request.legal_name == "Otro Nombre"

    def test_second_request_while_pending_fails(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "INVOICE_ALREADY_PENDING"

    def test_emits_invoice_requested_event(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        event = conn.execute(
            "SELECT event_name FROM sales_outbox WHERE event_name='SALE_INVOICE_REQUESTED'"
            " AND payload_json LIKE ?", (f'%"entity_id": "{sale_id}"%',)).fetchone()
        assert event is not None


class TestInvoiceStatusResolution:
    def test_mark_issued_requires_permission(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        req_result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        denied = SalesAuthorizationPolicy(DenyAllSalesPermissionCheckerForTests())
        result = MarkInvoiceIssuedUseCase(denied).execute(
            conn, sale_id=sale_id, invoice_request_id=req_result.data["invoice_request_id"],
            uuid_fiscal="ABC-123", actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "PERMISSION_DENIED"

    def test_mark_issued_resolves_the_request(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        req_result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        result = MarkInvoiceIssuedUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, invoice_request_id=req_result.data["invoice_request_id"],
            uuid_fiscal="ABC-123", actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is True
        request = SaleRepository(conn).get(sale_id).invoice_requests[0]
        assert request.status is InvoiceStatus.ISSUED
        assert request.uuid_fiscal == "ABC-123"

    def test_mark_error_resolves_with_real_message_and_allows_retry(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        req_result = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        MarkInvoiceErrorUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, invoice_request_id=req_result.data["invoice_request_id"],
            error_message="Tiempo de espera del PAC agotado", actor_user_id=cashier,
            operation_id=new_uuid())

        retry = RequestInvoiceUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        assert retry.success is True
        sale = SaleRepository(conn).get(sale_id)
        assert len(sale.invoice_requests) == 2
        assert sale.invoice_requests[0].status is InvoiceStatus.ERROR
        assert sale.invoice_requests[0].error_message == "Tiempo de espera del PAC agotado"
        assert sale.invoice_requests[1].status is InvoiceStatus.REQUESTED

    def test_mark_issued_fails_for_unknown_request_id(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        result = MarkInvoiceIssuedUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, invoice_request_id=new_uuid(), uuid_fiscal="ABC-123",
            actor_user_id=cashier, operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "INVOICE_REQUEST_NOT_FOUND"
