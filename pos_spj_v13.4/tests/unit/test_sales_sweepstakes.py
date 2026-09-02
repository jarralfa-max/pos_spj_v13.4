"""SET-15 cutover — real raffle ticket issuance (at checkout) and
printing (via reprint) for `sales_pos`. `SalesSweepstakesClient` needs no
identity bridge (unlike `SalesLoyaltyClient`) — see its own docstring.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest

from backend.application.loyalty.authorization import LoyaltyAuthorizationPolicy
from backend.application.sales.authorization import AllowAllSalesPermissionCheckerForTests, SalesAuthorizationPolicy
from backend.application.sales.dto import SaleDTO
from backend.application.sales.use_cases.cart_use_cases import AddSaleLineUseCase, StartSaleUseCase
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.receipt_use_cases import ReprintReceiptUseCase
from backend.application.sweepstakes.use_cases.campaign_use_cases import (
    ActivateSweepstakesCampaignUseCase,
    ApproveSweepstakesCampaignUseCase,
    ConfigureSweepstakesRuleUseCase,
    CreateSweepstakesCampaignUseCase,
)
from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.infrastructure.db.repositories.sales.sale_repository import SaleRepository
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import SweepstakesUnitOfWork
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema
from backend.infrastructure.integrations.sales_sweepstakes_client import SalesSweepstakesClient
from backend.shared.ids import new_uuid
from core.services.loyalty_service import LoyaltyService


def _allow_all() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


class _FakePrinterService:
    def __init__(self) -> None:
        self.last_ticket_data = None
        self.raffle_tickets_printed: list[dict] = []

    def print_ticket(self, ticket_data, on_success=None, on_error=None) -> str:
        self.last_ticket_data = ticket_data
        if on_success:
            on_success()
        return "job-42"

    def print_raffle_ticket(self, raffle_ticket_data, on_success=None, on_error=None) -> str:
        self.raffle_tickets_printed.append(raffle_ticket_data)
        return "job-raffle"


class _RaisingPrinterService(_FakePrinterService):
    def print_raffle_ticket(self, raffle_ticket_data, on_success=None, on_error=None) -> str:
        raise RuntimeError("boom: printer offline")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_sweepstakes_schema(c)
    c.execute("CREATE TABLE print_job_log (id TEXT PRIMARY KEY, job_id TEXT)")
    c.commit()
    yield c
    c.close()


def _mk_raffle(conn, *, branch_id: str, **rules) -> str:
    svc = LoyaltyService(conn, sucursal_id=branch_id)
    return svc.create_raffle_with_rules(
        {
            "nombre": "Rifa de Verano", "premio": "Refrigerador", "premio_costo_estimado": 10,
            "presupuesto_maximo": 20, "ventas_objetivo": 20, "monto_por_boleto": 10,
            "estado": "activa", "financial_status": "reservada",
            "fecha_inicio": "2020-01-01 00:00:00", "fecha_fin": "2099-12-31 23:59:59",
            "sucursal_id": branch_id,
        },
        rules, [{"nombre": "P1", "cantidad": 5, "costo_estimado": 10, "orden": 1}],
        {"branches": [branch_id]},
    )


def _completed_sale(conn, *, price="100.00", branch_id=None):
    branch_id = branch_id or new_uuid()
    cashier = new_uuid()
    sale_id = StartSaleUseCase(_allow_all()).execute(
        conn, branch_id=branch_id, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    AddSaleLineUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid())
    BeginSaleCheckoutUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    RecordSalePaymentUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, method="CASH", amount=Decimal(price),
        actor_user_id=cashier, operation_id=new_uuid())
    result = CheckoutSaleUseCase(_allow_all()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id, cashier, branch_id


class TestSalesSweepstakesClient:
    def test_issues_a_real_ticket_for_an_eligible_sale(self, conn):
        branch_id = new_uuid()
        _mk_raffle(conn, branch_id=branch_id, ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id, _cashier, _branch = _completed_sale(conn, price="100.00", branch_id=branch_id)
        sale = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))

        SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=sale)

        tickets = LoyaltyService(conn)._app.repo.get_tickets_for_venta(sale_id)
        assert len(tickets) == 1

    def test_no_active_raffle_is_a_silent_no_op(self, conn):
        sale_id, _cashier, _branch = _completed_sale(conn)
        sale = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))
        SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=sale)  # must not raise
        assert LoyaltyService(conn)._app.repo.get_tickets_for_venta(sale_id) == []

    def test_get_printable_tickets_for_sale_returns_what_was_issued(self, conn):
        branch_id = new_uuid()
        _mk_raffle(conn, branch_id=branch_id, ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id, _cashier, _branch = _completed_sale(conn, price="100.00", branch_id=branch_id)
        sale = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))
        SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=sale)

        payloads = SalesSweepstakesClient(conn).get_printable_tickets_for_sale(sale_id=sale_id)
        assert len(payloads) == 1
        assert payloads[0]["venta_id"] == sale_id


class TestCheckoutIssuesRaffleTickets:
    def test_qualifying_sale_issues_a_real_ticket_at_checkout(self, conn):
        branch_id = new_uuid()
        _mk_raffle(conn, branch_id=branch_id, ticket_strategy="per_sale", tickets_per_sale=1)
        cashier = new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("100.00"), actor_user_id=cashier, operation_id=new_uuid())
        BeginSaleCheckoutUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        RecordSalePaymentUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, method="CASH", amount=Decimal("100.00"),
            actor_user_id=cashier, operation_id=new_uuid())

        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is True
        assert result.data["raffle_issue_error"] is None
        assert len(LoyaltyService(conn)._app.repo.get_tickets_for_venta(sale_id)) == 1

    def test_raffle_issuance_failure_never_blocks_checkout(self, conn, monkeypatch):
        branch_id = new_uuid()
        cashier = new_uuid()
        sale_id = StartSaleUseCase(_allow_all()).execute(
            conn, branch_id=branch_id, cashier_user_id=cashier,
            operation_id=new_uuid(), actor_user_id=cashier).entity_id
        AddSaleLineUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
            unit_price=Decimal("50.00"), actor_user_id=cashier, operation_id=new_uuid())
        BeginSaleCheckoutUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
        RecordSalePaymentUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, method="CASH", amount=Decimal("50.00"),
            actor_user_id=cashier, operation_id=new_uuid())

        class _RaisingClient:
            def __init__(self, connection): pass
            def issue_tickets_for_sale(self, **kwargs): raise RuntimeError("boom")

        monkeypatch.setattr(
            "backend.application.sales.use_cases.checkout_use_cases.SalesSweepstakesClient", _RaisingClient)

        result = CheckoutSaleUseCase(_allow_all()).execute(
            conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())

        assert result.success is True
        assert "boom" in result.data["raffle_issue_error"]


class TestSalesGrantsNewSweepstakesEntries:
    """LOY-24 (§54): `SalesSweepstakesClient` also grants entries in the
    NEW `sweepstakes` bounded context, alongside (not instead of) the
    legacy raffle call above."""

    def _active_campaign_with_rule(self, conn, *, amount_per_ticket="100"):
        from decimal import Decimal
        auth = LoyaltyAuthorizationPolicy.permissive_for_tests()
        create = CreateSweepstakesCampaignUseCase(auth).execute(
            conn, code="NEWPROMO", name="Promo nueva", actor_user_id=new_uuid(),
            operation_id=new_uuid())
        ApproveSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        ActivateSweepstakesCampaignUseCase(auth).execute(
            conn, campaign_id=create.entity_id, actor_user_id=new_uuid(),
            operation_id=new_uuid())
        ConfigureSweepstakesRuleUseCase(auth).execute(
            conn, campaign_id=create.entity_id, entry_method=SweepstakesEntryMethod.PURCHASE_AMOUNT,
            actor_user_id=new_uuid(), operation_id=new_uuid(),
            amount_per_ticket=Decimal(amount_per_ticket))
        return create.entity_id

    def test_grants_entry_for_a_sale_with_customer_and_active_campaign(self, conn):
        campaign_id = self._active_campaign_with_rule(conn, amount_per_ticket="100")
        sale_id, _cashier, branch_id = _completed_sale(conn, price="350.00")
        customer_id = new_uuid()
        real_sale = SaleRepository(conn).get(sale_id)
        sale = SaleDTO.from_entity(real_sale)
        # Simulate an already-assigned customer without depending on Customer
        # Master's own existence check (out of scope for this integration test).
        sale = replace(sale, customer_id=customer_id)

        SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=sale)

        with SweepstakesUnitOfWork(conn) as uow:
            entries = uow.entries.list_for_customer(campaign_id, customer_id)
        assert len(entries) == 1
        assert entries[0].chances_granted == 3
        assert entries[0].source_sale_id == sale_id

    def test_no_customer_grants_nothing(self, conn):
        campaign_id = self._active_campaign_with_rule(conn, amount_per_ticket="100")
        sale_id, _cashier, _branch = _completed_sale(conn, price="350.00")
        sale = SaleDTO.from_entity(SaleRepository(conn).get(sale_id))
        assert sale.customer_id is None

        SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=sale)  # must not raise

    def test_no_active_campaign_is_a_silent_no_op(self, conn):
        sale_id, _cashier, _branch = _completed_sale(conn, price="350.00")
        sale = replace(SaleDTO.from_entity(SaleRepository(conn).get(sale_id)), customer_id=new_uuid())
        SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=sale)  # must not raise


class TestReprintPrintsRaffleTickets:
    def test_reprint_prints_issued_raffle_tickets_alongside_the_receipt(self, conn):
        branch_id = new_uuid()
        _mk_raffle(conn, branch_id=branch_id, ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id, cashier, _branch = _completed_sale(conn, price="100.00", branch_id=branch_id)
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert result.data["raffle_tickets_printed"] == 1
        assert len(printer.raffle_tickets_printed) == 1
        assert printer.raffle_tickets_printed[0]["venta_id"] == sale_id

    def test_no_tickets_issued_prints_nothing_extra(self, conn):
        sale_id, cashier, _branch = _completed_sale(conn)
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert result.data["raffle_tickets_printed"] == 0
        assert printer.raffle_tickets_printed == []

    def test_raffle_ticket_print_failure_never_blocks_the_receipt(self, conn):
        branch_id = new_uuid()
        _mk_raffle(conn, branch_id=branch_id, ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id, cashier, _branch = _completed_sale(conn, price="100.00", branch_id=branch_id)
        printer = _RaisingPrinterService()

        result = ReprintReceiptUseCase(_allow_all()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert result.data["job_id"] == "job-42"
        assert result.data["raffle_tickets_printed"] == 0
