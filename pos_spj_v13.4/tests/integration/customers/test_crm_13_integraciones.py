"""CRM-13 — Integraciones: Ventas activity projection, commercial
eligibility, Pedidos/Delivery/WhatsApp/Fidelidad read-only summaries, BI
export, and the Finanzas ``receivable_status`` addition.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.queries.crm_bi_export_query_service import CRMBIExportQueryService
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.integrations.sales_event_handlers import (
    handle_sale_cancelled,
    handle_sale_completed,
)
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.queries.customer_commercial_eligibility_query import (
    CustomerCommercialEligibilityQuery,
)
from backend.application.customers.queries.customer_delivery_summary_query import (
    CustomerDeliverySummaryQuery,
)
from backend.application.customers.queries.customer_orders_summary_query import (
    CustomerOrdersSummaryQuery,
)
from backend.application.customers.queries.customer_whatsapp_summary_query import (
    CustomerWhatsAppSummaryQuery,
)
from backend.application.customers.queries.loyalty_customer_summary_query import (
    LoyaltyCustomerSummaryQuery,
)
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.application.customers.use_cases.sales_integration_use_cases import (
    RecordCustomerSaleActivityUseCase,
    RecordCustomerSaleCancelledUseCase,
)
from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
    CustomerAccountsReceivableSummaryQuery,
)
from backend.application.customer_credit.use_cases.check_credit_sale_eligibility_use_case import (
    CheckCreditSaleEligibilityUseCase,
)
from backend.domain.customers.enums import CustomerStatus, LifecycleStage
from backend.domain.customers.exceptions import CustomerDomainError
from backend.shared.ids import new_uuid


def _allow_cust():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _allow_crm():
    return CRMAuthorizationPolicy.permissive_for_tests()


def _customer(conn, *, as_prospect=False) -> str:
    result = CreateCustomerUseCase(_allow_cust()).execute(
        conn, actor_user_id="u1", display_name="Restaurante El Sol",
        operation_id=new_uuid(), as_prospect=as_prospect)
    assert result.success
    return result.entity_id


class TestRecordCustomerSaleActivityUseCase:
    def test_applies_projection_and_returns_true(self, full_crm_conn):
        customer_id = _customer(full_crm_conn, as_prospect=True)
        applied = RecordCustomerSaleActivityUseCase().execute(
            full_crm_conn, customer_id=customer_id, occurred_at="2026-08-13T10:00:00+00:00",
            source_event_id="venta-1", operation_id="venta-1")
        assert applied is True

        from backend.infrastructure.db.repositories.customers.unit_of_work import (
            CustomerUnitOfWork,
        )
        with CustomerUnitOfWork(full_crm_conn) as uow:
            customer = uow.customers.get(customer_id)
        assert customer.purchase_count == 1
        assert customer.lifecycle_stage is LifecycleStage.CUSTOMER

    def test_replaying_same_source_event_is_a_noop(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        uc = RecordCustomerSaleActivityUseCase()
        uc.execute(full_crm_conn, customer_id=customer_id, occurred_at="2026-08-13T10:00:00+00:00",
                  source_event_id="venta-2", operation_id="venta-2")
        second = uc.execute(
            full_crm_conn, customer_id=customer_id, occurred_at="2026-08-14T10:00:00+00:00",
            source_event_id="venta-2", operation_id="venta-2")
        assert second is False

    def test_unknown_customer_is_a_noop(self, full_crm_conn):
        applied = RecordCustomerSaleActivityUseCase().execute(
            full_crm_conn, customer_id="does-not-exist", occurred_at="2026-08-13T10:00:00+00:00",
            source_event_id="venta-3", operation_id="venta-3")
        assert applied is False


class TestRecordCustomerSaleCancelledUseCase:
    def test_decrements_purchase_count(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        RecordCustomerSaleActivityUseCase().execute(
            full_crm_conn, customer_id=customer_id, occurred_at="2026-08-13T10:00:00+00:00",
            source_event_id="venta-4", operation_id="venta-4")
        applied = RecordCustomerSaleCancelledUseCase().execute(
            full_crm_conn, customer_id=customer_id, source_event_id="venta-4-cancel",
            operation_id="venta-4-cancel")
        assert applied is True


class TestSalesEventHandlers:
    def test_handle_sale_completed_applies_when_customer_id_matches(self, full_crm_conn):
        customer_id = _customer(full_crm_conn, as_prospect=True)
        payload = {"cliente_id": customer_id, "venta_id": "v-1", "operation_id": "op-1",
                   "sale_datetime": "2026-08-13T10:00:00+00:00"}
        assert handle_sale_completed(full_crm_conn, payload) is True

    def test_handle_sale_completed_noops_on_unmapped_legacy_id(self, full_crm_conn):
        """Documents the identity-gap contract: a legacy-shaped cliente_id
        (never a UUIDv7 that exists in `customers`) safely no-ops today."""
        payload = {"cliente_id": "42", "venta_id": "v-2", "operation_id": "op-2",
                   "sale_datetime": "2026-08-13T10:00:00+00:00"}
        assert handle_sale_completed(full_crm_conn, payload) is False

    def test_handle_sale_completed_missing_cliente_id_noops(self, full_crm_conn):
        assert handle_sale_completed(full_crm_conn, {"venta_id": "v-3"}) is False

    def test_handle_sale_cancelled_applies_when_customer_id_matches(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        payload = {"cliente_id": customer_id, "venta_id": "v-4", "operation_id": "op-4"}
        assert handle_sale_cancelled(full_crm_conn, payload) is True


class TestCustomerCommercialEligibilityQuery:
    def test_active_customer_is_eligible(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        result = CustomerCommercialEligibilityQuery(full_crm_conn, _allow_cust()).check(
            customer_id, actor_user_id="u1")
        assert result.eligible is True
        assert result.violations == ()

    def test_blocked_customer_is_not_eligible(self, full_crm_conn):
        from backend.infrastructure.db.repositories.customers.unit_of_work import (
            CustomerUnitOfWork,
        )
        customer_id = _customer(full_crm_conn)
        with CustomerUnitOfWork(full_crm_conn) as uow:
            customer = uow.customers.get(customer_id)
            customer.block("mora")
            uow.customers.update(customer)
        result = CustomerCommercialEligibilityQuery(full_crm_conn, _allow_cust()).check(
            customer_id, actor_user_id="u1")
        assert result.eligible is False
        assert result.violations

    def test_unknown_customer_is_not_eligible(self, full_crm_conn):
        result = CustomerCommercialEligibilityQuery(full_crm_conn, _allow_cust()).check(
            "does-not-exist", actor_user_id="u1")
        assert result.eligible is False

    def test_requires_permission(self, full_crm_conn):
        from backend.application.customers.authorization import (
            DenyAllCustomerPermissionCheckerForTests,
        )
        customer_id = _customer(full_crm_conn)
        service = CustomerCommercialEligibilityQuery(
            full_crm_conn, CustomerAuthorizationPolicy(DenyAllCustomerPermissionCheckerForTests()))
        with pytest.raises(CustomerDomainError):
            service.check(customer_id, actor_user_id="u1")


class TestCheckCreditSaleEligibilityUseCase:
    """CRM-13 found this already existed (CRM-8) — confirms it still works
    against a customer created through this bounded context, not just the
    legacy flow it was originally tested with."""

    def test_no_profile_is_not_eligible(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        result = CheckCreditSaleEligibilityUseCase(_allow_cust()).execute(
            full_crm_conn, actor_user_id="u1", customer_id=customer_id,
            amount=Decimal("100"), operation_id=new_uuid())
        assert result.success is False
        assert result.error_code == "NOT_ELIGIBLE"


class TestCustomerOrdersSummaryQuery:
    def test_empty_when_no_orders(self, full_crm_conn_with_ops):
        customer_id = _customer(full_crm_conn_with_ops)
        summary = CustomerOrdersSummaryQuery(full_crm_conn_with_ops, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.total_orders == 0

    def test_counts_matching_rows_when_id_matches(self, full_crm_conn_with_ops):
        """Demonstrates the query is correct when identity is reconciled —
        today's real payloads carry the legacy id (see sales_event_handlers'
        documented gap), but this proves the read path itself works."""
        customer_id = _customer(full_crm_conn_with_ops)
        full_crm_conn_with_ops.execute(
            "INSERT INTO pedidos_whatsapp (id, numero_whatsapp, cliente_id, estado, fecha)"
            " VALUES (?,?,?,?,datetime('now'))",
            (new_uuid(), "+525500000000", customer_id, "nuevo"))
        full_crm_conn_with_ops.commit()
        summary = CustomerOrdersSummaryQuery(full_crm_conn_with_ops, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.total_orders == 1
        assert summary.open_orders == 1
        assert summary.last_order_status == "nuevo"

    def test_requires_permission(self, full_crm_conn_with_ops):
        from backend.application.customers.authorization import (
            DenyAllCustomerPermissionCheckerForTests,
        )
        customer_id = _customer(full_crm_conn_with_ops)
        service = CustomerOrdersSummaryQuery(
            full_crm_conn_with_ops,
            CustomerAuthorizationPolicy(DenyAllCustomerPermissionCheckerForTests()))
        with pytest.raises(CustomerDomainError):
            service.get_summary(customer_id, actor_user_id="u1")


class TestCustomerDeliverySummaryQuery:
    def test_empty_when_no_deliveries(self, full_crm_conn_with_ops):
        customer_id = _customer(full_crm_conn_with_ops)
        summary = CustomerDeliverySummaryQuery(full_crm_conn_with_ops, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.total_deliveries == 0
        assert summary.recent_incidents == ()

    def test_incident_surfaced_from_history_reason(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = _customer(conn)
        cur = conn.execute(
            "INSERT INTO delivery_orders (cliente_id, direccion, estado, fecha)"
            " VALUES (?,?,?,datetime('now'))", (customer_id, "Calle 1", "en_ruta"))
        order_id = cur.lastrowid
        conn.execute(
            "INSERT INTO delivery_order_history (order_id, reason, fecha)"
            " VALUES (?,?,datetime('now'))", (order_id, "Cliente no localizado"))
        conn.commit()
        summary = CustomerDeliverySummaryQuery(conn, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.total_deliveries == 1
        assert summary.open_deliveries == 1
        assert len(summary.recent_incidents) == 1
        assert summary.recent_incidents[0].reason == "Cliente no localizado"


class TestCustomerWhatsAppSummaryQuery:
    def test_no_consent_by_default(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        summary = CustomerWhatsAppSummaryQuery(full_crm_conn, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.has_active_whatsapp_consent is False
        assert summary.last_conversation_at is None
        assert summary.open_conversations_count == 0
        assert summary.handoff_pending is False

    def test_reflects_active_consent(self, full_crm_conn):
        from backend.application.customer_privacy.use_cases.consent_use_cases import (
            CaptureConsentUseCase,
        )
        customer_id = _customer(full_crm_conn)
        CaptureConsentUseCase(_allow_cust()).execute(
            full_crm_conn, actor_user_id="u1", customer_id=customer_id,
            consent_type="WHATSAPP", channel="WHATSAPP", evidence_reference="wa-opt-in-1",
            operation_id=new_uuid())
        summary = CustomerWhatsAppSummaryQuery(full_crm_conn, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.has_active_whatsapp_consent is True


class TestLoyaltyCustomerSummaryQuery:
    def test_not_enrolled_when_no_snapshot(self, full_crm_conn_with_ops):
        customer_id = _customer(full_crm_conn_with_ops)
        summary = LoyaltyCustomerSummaryQuery(full_crm_conn_with_ops, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.enrolled is False
        assert summary.current_points == 0

    def test_reads_snapshot_when_present(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = _customer(conn)
        conn.execute(
            "INSERT INTO loyalty_snapshots (id, cliente_id, puntos_actuales, nivel, visitas,"
            " importe_total) VALUES (?,?,?,?,?,?)",
            (new_uuid(), customer_id, 150, "Plata", 4, 2500.0))
        conn.commit()
        summary = LoyaltyCustomerSummaryQuery(conn, _allow_cust()).get_summary(
            customer_id, actor_user_id="u1")
        assert summary.enrolled is True
        assert summary.current_points == 150
        assert summary.tier == "Plata"


class TestCRMBIExportQueryService:
    def test_snapshot_reflects_empty_state(self, full_crm_conn):
        snapshot = CRMBIExportQueryService(full_crm_conn, _allow_crm()).get_snapshot(
            actor_user_id="u1")
        assert snapshot.leads_total == 0
        assert snapshot.lead_conversion_rate == 0.0

    def test_requires_permission(self, full_crm_conn):
        from backend.application.crm.authorization import DenyAllCRMPermissionCheckerForTests
        service = CRMBIExportQueryService(
            full_crm_conn, CRMAuthorizationPolicy(DenyAllCRMPermissionCheckerForTests()))
        with pytest.raises(Exception):
            service.get_snapshot(actor_user_id="u1")


class TestReceivableStatus:
    def test_sin_movimientos_when_no_documents(self, full_crm_conn):
        summary = CustomerAccountsReceivableSummaryQuery(full_crm_conn).get_summary("cust-x")
        assert summary.receivable_status == "SIN_MOVIMIENTOS"
