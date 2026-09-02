"""SET-13 cutover — real loyalty/marketing content on live tickets,
against a real (in-memory) SQLite schema combining Sales, Customer
Master/CRM, the legacy loyalty ledger, and the born-clean Document
Output/Device Management schema. Two properties under test:

1. With nothing configured (the pre-SET-13 state), a reprint's ticket
   payload is unchanged — no `loyalty`/`fomo_messages` keys at all.
2. With a real customer, real loyalty points, and real active campaigns
   configured, a reprint's `printer.last_ticket_data["loyalty"]`/
   `["fomo_messages"]` reflect them — and an unexpected failure inside
   either integration never blocks the real reprint.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.sales.authorization import AllowAllSalesPermissionCheckerForTests, SalesAuthorizationPolicy
from backend.application.sales.use_cases.cart_use_cases import (
    AddSaleLineUseCase,
    AssignCustomerToSaleUseCase,
    StartSaleUseCase,
)
from backend.application.sales.use_cases.checkout_use_cases import CheckoutSaleUseCase
from backend.application.sales.use_cases.customer_use_cases import QuickCreateCustomerForSaleUseCase
from backend.application.sales.use_cases.lifecycle_use_cases import BeginSaleCheckoutUseCase
from backend.application.sales.use_cases.payment_use_cases import RecordSalePaymentUseCase
from backend.application.sales.use_cases.receipt_use_cases import ReprintReceiptUseCase
from backend.application.use_cases.configuracion.marketing_campaign_use_cases import CreateMarketingCampaignUseCase
from backend.domain.document_output.enums import RuleComparator
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema
from backend.infrastructure.db.schema.sales_schema import create_sales_schema
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _allow_all_sales() -> SalesAuthorizationPolicy:
    return SalesAuthorizationPolicy(AllowAllSalesPermissionCheckerForTests())


def _allow_all_customers() -> CustomerAuthorizationPolicy:
    return CustomerAuthorizationPolicy.permissive_for_tests()


class _FakePrinterService:
    def __init__(self) -> None:
        self.last_ticket_data = None

    def print_ticket(self, ticket_data, on_success=None, on_error=None) -> str:
        self.last_ticket_data = ticket_data
        if on_success:
            on_success()
        return "job-42"


class _RaisingSalesMarketingClient:
    def __init__(self, connection) -> None:
        pass

    def select_ticket_messages(self, **kwargs):
        raise RuntimeError("boom: unexpected marketing selection failure")


@pytest.fixture
def conn():
    # make_db() already applies migrations 057/092 (real loyalty_ledger)
    # and m000 (real clientes) — reuse those, don't hand-roll duplicates.
    connection = make_db()
    create_sales_schema(connection)
    create_customers_crm_schema(connection)
    connection.commit()
    yield connection
    connection.close()


def _award_points(conn, *, legacy_customer_id: str, points: int) -> None:
    conn.execute(
        "INSERT INTO loyalty_ledger (id, cliente_id, tipo, puntos, saldo_post) VALUES (?, ?, 'acumulacion', ?, ?)",
        (new_uuid(), legacy_customer_id, points, points))
    conn.commit()


def _sale_with_customer(conn, *, customer_id: str | None, price="100.00") -> tuple[str, str]:
    branch, cashier = new_uuid(), new_uuid()
    sale_id = StartSaleUseCase(_allow_all_sales()).execute(
        conn, branch_id=branch, cashier_user_id=cashier,
        operation_id=new_uuid(), actor_user_id=cashier).entity_id
    if customer_id is not None:
        AssignCustomerToSaleUseCase(_allow_all_sales()).execute(
            conn, sale_id=sale_id, customer_id=customer_id, actor_user_id=cashier, operation_id=new_uuid())
    AddSaleLineUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, product_id=new_uuid(), quantity=Decimal("1"),
        unit_price=Decimal(price), actor_user_id=cashier, operation_id=new_uuid(),
        product_snapshot={"name": "Bistec"})
    BeginSaleCheckoutUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    RecordSalePaymentUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, method="CASH", amount=Decimal(price),
        actor_user_id=cashier, operation_id=new_uuid())
    result = CheckoutSaleUseCase(_allow_all_sales()).execute(
        conn, sale_id=sale_id, actor_user_id=cashier, operation_id=new_uuid())
    assert result.success, result.message
    return sale_id, cashier


class TestNothingConfiguredIsUnchanged:
    def test_reprint_payload_has_no_loyalty_or_messages_keys(self, conn):
        sale_id, cashier = _sale_with_customer(conn, customer_id=None)
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all_sales()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert "loyalty" not in printer.last_ticket_data
        assert "fomo_messages" not in printer.last_ticket_data


class TestConfiguredLoyaltyAndMarketing:
    def test_reprint_shows_real_loyalty_summary_and_campaign_messages(self, conn):
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            EnsureLegacyCustomerBridgeUseCase,
        )

        customer_id = QuickCreateCustomerForSaleUseCase(_allow_all_customers()).execute(
            conn, actor_user_id=new_uuid(), operation_id=new_uuid(), display_name="Ana Torres").entity_id
        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        conn.execute("INSERT OR IGNORE INTO clientes (id, nombre) VALUES (?, 'Bridge stub')", (legacy_id,))
        conn.commit()
        _award_points(conn, legacy_customer_id=legacy_id, points=30)

        CreateMarketingCampaignUseCase(conn).execute(
            code="low_balance", category="FOMO", message_template="¡Solo {points_balance} puntos, canjéalos ya!",
            rules=[CampaignRule.create(
                metric="points_balance", comparator=RuleComparator.LESS_THAN, threshold=Decimal("50"))],
        )
        CreateMarketingCampaignUseCase(conn).execute(
            code="thanks", category="LOYALTY", message_template="Gracias por tu compra, {points_balance} pts.",
        )

        sale_id, cashier = _sale_with_customer(conn, customer_id=customer_id, price="200.00")
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all_sales()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        payload = printer.last_ticket_data
        assert payload["loyalty"]["puntos_totales"] == 30
        assert payload["loyalty"]["available"] is True
        assert any("30" in msg for msg in payload["fomo_messages"])
        assert any("Gracias" in msg for msg in payload["fomo_messages"])

    def test_fomo_campaign_without_customer_requirement_still_shows_for_anonymous_sale(self, conn):
        CreateMarketingCampaignUseCase(conn).execute(
            code="big_subtotal", category="FOMO", message_template="¡Compra grande detectada!",
            rules=[CampaignRule.create(
                metric="subtotal", comparator=RuleComparator.GREATER_THAN_OR_EQUAL, threshold=Decimal("50"))],
        )
        sale_id, cashier = _sale_with_customer(conn, customer_id=None, price="200.00")
        printer = _FakePrinterService()

        result = ReprintReceiptUseCase(_allow_all_sales()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert "loyalty" not in printer.last_ticket_data  # no customer assigned
        assert "¡Compra grande detectada!" in printer.last_ticket_data["fomo_messages"]

    def test_marketing_client_raising_unexpectedly_does_not_break_a_real_reprint(self, conn, monkeypatch):
        sale_id, cashier = _sale_with_customer(conn, customer_id=None)
        printer = _FakePrinterService()
        monkeypatch.setattr(
            "backend.application.sales.use_cases.receipt_use_cases.SalesMarketingClient",
            _RaisingSalesMarketingClient)

        result = ReprintReceiptUseCase(_allow_all_sales()).execute(
            conn, printer, sale_id=sale_id, cajero_nombre="Ana", actor_user_id=cashier,
            operation_id=new_uuid())

        assert result.success is True
        assert result.data["job_id"] == "job-42"
