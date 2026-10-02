"""Devolución PARCIAL: reembolso en Caja y asiento en Finanzas (2026-10-02).

Decisiones del usuario que estas pruebas fijan:

* el reembolso sale por el MÉTODO ORIGINAL, efectivo primero; lo pagado a
  crédito baja la deuda (nota de crédito sobre la CxC);
* el importe devuelto es lo que el cliente PAGÓ por esa parte, incluido su
  pedazo del descuento a nivel venta (antes se reembolsaba de más);
* contabilidad en espejo de la venta: ingreso, descuento, medio de reembolso y
  costo de venta.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.refund_integration import CashRefundIntegrationService
from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    InventoryAuthorizationPolicy,
)
from backend.application.sales.authorization import (
    AllowAllSalesPermissionCheckerForTests,
    SalesAuthorizationPolicy,
)
from backend.application.sales.integrations.wiring import dispatch_sales_outbox, wire_sales
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.discount_use_cases import ApplySaleDiscountPercentUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.return_use_cases import ReturnSaleLineUseCase
from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.domain.cash_register.policies.security_policies import CashMonetaryLimitPolicy
from backend.domain.pricing.entities.product_cost import ProductCost
from backend.domain.pricing.value_objects.money import Money
from backend.domain.sales.services import refund_service
from backend.infrastructure.db.repositories.pricing.pricing_repository import PricingRepository
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.events.application_bus import ApplicationEventBus
from backend.shared.ids import new_uuid
from tests.integration._pos_ready import open_cash_shift, stock_product


# ── reparto (dominio puro) ───────────────────────────────────────────────────

class _Line:
    def __init__(self, line_id, line_total):
        self.id, self.line_total = line_id, Decimal(line_total)


class _Pay:
    def __init__(self, method, amount):
        self.method, self.amount = method, Decimal(amount)


def test_line_nets_absorb_the_sale_level_discount_and_add_up_exactly():
    netos = refund_service.line_net_values(
        [_Line("a", "100"), _Line("b", "100"), _Line("c", "100")], total=Decimal("100"))
    assert sum(netos.values()) == Decimal("100.00")
    assert sorted(netos.values()) == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_cash_is_refunded_first_net_of_change():
    pagos = refund_service.net_payments(
        [_Pay("CARD", "80"), _Pay("CASH", "150")], change=Decimal("30"))
    assert pagos == [("CASH", Decimal("120")), ("CARD", Decimal("80"))]
    assert refund_service.allocate_refund(pagos, already_refunded=Decimal("0"),
                                          amount=Decimal("50")) == [("CASH", Decimal("50"))]


def test_successive_returns_never_refund_the_same_cash_twice():
    pagos = [("CASH", Decimal("120")), ("CARD", Decimal("80"))]
    primera = refund_service.allocate_refund(pagos, already_refunded=Decimal("0"),
                                             amount=Decimal("100"))
    segunda = refund_service.allocate_refund(pagos, already_refunded=Decimal("100"),
                                             amount=Decimal("50"))
    assert primera == [("CASH", Decimal("100"))]
    assert segunda == [("CASH", Decimal("20")), ("CARD", Decimal("30"))]


def test_the_last_return_of_a_line_closes_its_rounding_remainder():
    tercio = refund_service.return_amount(
        line_net=Decimal("100.00"), line_quantity=Decimal("3"),
        already_returned_quantity=Decimal("0"), already_returned_amount=Decimal("0"),
        quantity=Decimal("1"))
    resto = refund_service.return_amount(
        line_net=Decimal("100.00"), line_quantity=Decimal("3"),
        already_returned_quantity=Decimal("1"), already_returned_amount=tercio,
        quantity=Decimal("2"))
    assert tercio + resto == Decimal("100.00")


# ── de punta a punta ─────────────────────────────────────────────────────────

class _Allow:
    def has_permission(self, user_id, permission_code):
        return True

    def can_access_branch(self, *, user_id, branch_id):
        return True


def _sales_auth():
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _inv_auth():
    return InventoryAuthorizationPolicy(AllowAllInventoryPermissionCheckerForTests())


def _cash_refunds(limit="5000"):
    return CashRefundIntegrationService(
        CashAuthorizationPolicy(permissions=_Allow(), scopes=_Allow()),
        CashMonetaryLimitPolicy(approval_threshold=Decimal(limit), hard_cap=Decimal(limit)))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    for create in (create_sales_schema, create_products_schema, create_pricing_schema,
                   create_inventory_schema, create_finance_schema):
        create(c)
    bootstrap_finance(c)
    c.commit()
    yield c
    c.close()


@pytest.fixture
def bus(conn):
    local = ApplicationEventBus()
    wire_sales(local, conn)
    return local


def _venta(conn, *, branch, cashier, product, precio="100", cantidad="2", descuento=None,
           pago="200"):
    sale_id = StartSaleUseCase(_sales_auth()).execute(
        conn, branch_id=branch, cashier_user_id=cashier, operation_id=new_uuid(),
        actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_sales_auth()).execute(
        conn, sale_id=sale_id, product_id=product, quantity=Decimal(cantidad),
        unit_price=Decimal(precio), actor_user_id=cashier, operation_id=new_uuid())
    if descuento:
        assert ApplySaleDiscountPercentUseCase(_sales_auth()).execute(
            conn, sale_id=sale_id, discount_percent=Decimal(descuento), actor_user_id=cashier,
            operation_id=new_uuid()).success
    BeginSaleCheckoutUseCase(_sales_auth()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    RecordSalePaymentUseCase(_sales_auth()).execute(
        conn, sale_id=sale_id, method="CASH", amount=Decimal(pago), actor_user_id=cashier,
        operation_id=new_uuid())
    result = CheckoutSaleUseCase(_sales_auth(), _inv_auth()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id


def test_a_partial_cash_return_refunds_from_the_drawer_and_posts_the_mirror_entry(conn, bus):
    branch, gerente, product = new_uuid(), new_uuid(), new_uuid()
    open_cash_shift(conn, branch_id=branch, cashier_user_id=gerente)
    stock_product(conn, product_id=product, branch_id=branch, quantity="10")
    PricingRepository(conn).save_cost(ProductCost(
        product_id=product, branch_id=None, average_cost=Money(Decimal("50"))))
    conn.commit()
    sale_id = _venta(conn, branch=branch, cashier=gerente, product=product, descuento="10")
    dispatch_sales_outbox(conn, bus)
    line_id = SaleRepository(conn).get(sale_id).lines[0].id

    result = ReturnSaleLineUseCase(
        _sales_auth(), _inv_auth(), cash_refund_service=_cash_refunds()).execute(
        conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("1"), reason="mal estado",
        actor_user_id=gerente, authorizer_user_id=new_uuid(), operation_id=new_uuid())

    assert result.success, result.message
    # Pagó $180 por 2 piezas (10 % a toda la venta): devolver una son $90, no $100.
    assert result.data["amount"] == Decimal("90.00")
    assert result.data["refunds"] == [("CASH", Decimal("90.00"))]
    assert result.data["cash_effects_error"] is None
    refund = conn.execute(
        "SELECT amount FROM cash_ledger_entries WHERE related_sale_id=? AND"
        " movement_type='CASH_REFUND'", (sale_id,)).fetchone()
    assert Decimal(refund["amount"]) == Decimal("90.00")

    assert dispatch_sales_outbox(conn, bus)["failed"] == 0
    asiento = conn.execute(
        "SELECT id FROM journal_entries WHERE source_module='sales' AND posting_purpose="
        "'SALE_RETURN'").fetchone()
    lineas = conn.execute(
        "SELECT debit_amount, credit_amount FROM journal_lines WHERE journal_entry_id=?",
        (asiento["id"],)).fetchall()
    debe = sum(Decimal(l["debit_amount"] or "0") for l in lineas)
    haber = sum(Decimal(l["credit_amount"] or "0") for l in lineas)
    assert debe == haber == Decimal("100.00")  # ingreso 100 = descuento 10 + efectivo 90
    costo = conn.execute(
        "SELECT id FROM journal_entries WHERE posting_purpose='SALE_RETURN_COGS'").fetchone()
    assert costo is not None


def test_cash_refund_needs_the_returning_user_s_open_shift(conn):
    branch, cajero, gerente, product = new_uuid(), new_uuid(), new_uuid(), new_uuid()
    open_cash_shift(conn, branch_id=branch, cashier_user_id=cajero)
    stock_product(conn, product_id=product, branch_id=branch, quantity="10")
    sale_id = _venta(conn, branch=branch, cashier=cajero, product=product)
    line_id = SaleRepository(conn).get(sale_id).lines[0].id

    result = ReturnSaleLineUseCase(
        _sales_auth(), _inv_auth(), cash_refund_service=_cash_refunds()).execute(
        conn, sale_id=sale_id, line_id=line_id, quantity=Decimal("1"), reason="mal estado",
        actor_user_id=gerente, authorizer_user_id=new_uuid(), operation_id=new_uuid())

    assert result.error_code == "NO_OPEN_CASH_SHIFT"
    assert SaleRepository(conn).get(sale_id).returns == []


def test_a_credit_refund_lowers_the_customer_receivable_with_a_credit_note(conn):
    from datetime import date

    from backend.application.event_handlers.finance.sale_returned_handler import (
        SaleReturnedHandler,
    )
    from backend.application.use_cases.finance.receivable_use_cases import (
        CreateReceivableUseCase,
    )

    customer, sale_id = new_uuid(), new_uuid()
    CreateReceivableUseCase().execute(
        conn, customer_id=customer, amount="300", document_number="V-COR-000009",
        issue_date=date.today(), branch_id=None, source_module="sales",
        source_document_id=sale_id, operation_id=f"{sale_id}:receivable")

    SaleReturnedHandler(conn).handle({
        "event_id": new_uuid(), "operation_id": new_uuid(),
        "occurred_at": date.today().isoformat(), "sale_id": sale_id, "return_id": new_uuid(),
        "folio": "V-COR-000009", "customer_id": customer, "currency_code": "MXN",
        "amount": "100", "gross_amount": "100", "tax_amount": "0", "cogs_amount": "0",
        "refunds": [{"type": "ON_CREDIT", "amount": "100"}]})

    saldo = conn.execute(
        "SELECT outstanding_amount FROM receivables WHERE customer_id=?", (customer,)).fetchone()
    assert Decimal(saldo["outstanding_amount"]) == Decimal("200")
    nota = conn.execute(
        "SELECT document_type FROM financial_documents WHERE document_type='CREDIT_NOTE'"
    ).fetchone()
    assert nota is not None
