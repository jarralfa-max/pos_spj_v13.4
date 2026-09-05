# tests/test_composition_root.py — WA-4
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.composition_root import REQUIRED_SERVICES, WhatsAppCompositionRoot
from bootstrap.dependency_graph_validator import (
    CompositionRootValidationError,
    validate_composition_root,
)


@pytest.fixture()
def conn():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    yield connection
    connection.close()


@pytest.fixture()
def root(conn):
    return WhatsAppCompositionRoot(conn)


class TestWhatsAppCompositionRoot:
    def test_registers_all_required_services(self, root):
        for name in REQUIRED_SERVICES:
            assert root.registry.has(name)

    def test_validator_passes_on_freshly_built_root(self, root):
        validate_composition_root(root)  # no debe lanzar

    def test_accounts_accessor_returns_working_repository(self, root):
        from domain.whatsapp.entities.business_account import WhatsAppBusinessAccount
        from domain.whatsapp.enums import WhatsAppProvider

        account = WhatsAppBusinessAccount.create(
            provider=WhatsAppProvider.META,
            business_account_external_id="ext-1",
            display_name="SPJ",
        )
        root.accounts.save(account)
        assert root.accounts.get_by_id(account.id) is not None

    def test_numbers_accessor(self, root):
        assert root.numbers is not None

    def test_identities_accessor(self, root):
        assert root.identities is not None

    def test_conversations_accessor(self, root):
        assert root.conversations is not None

    def test_messages_accessor(self, root):
        assert root.messages is not None

    def test_secret_store_accessor_is_the_process_singleton(self, root):
        from config.settings import get_secret_store

        assert root.secret_store is get_secret_store()

    def test_provider_configurations_accessor(self, root):
        assert root.provider_configurations is not None

    def test_provider_gateway_accessor(self, root):
        from infrastructure.providers.meta_cloud_api.gateway import MetaCloudApiWhatsAppGateway

        assert isinstance(root.provider_gateway, MetaCloudApiWhatsAppGateway)

    def test_inbox_accessor(self, root):
        assert root.inbox is not None

    def test_webhook_processor_accessor(self, root):
        from infrastructure.webhooks.webhook_processor import WebhookProcessor

        assert isinstance(root.webhook_processor, WebhookProcessor)

    def test_inbox_worker_accessor(self, root):
        from infrastructure.webhooks.inbox_worker import InboxWorker

        assert isinstance(root.inbox_worker, InboxWorker)

    def test_conversation_engine_accessor(self, root):
        from application.conversation_engine import ConversationEngine

        assert isinstance(root.conversation_engine, ConversationEngine)

    def test_intent_resolution_service_accessor(self, root):
        from application.intent_resolution_service import IntentResolutionService

        assert isinstance(root.intent_resolution_service, IntentResolutionService)

    def test_order_drafts_accessor(self, root):
        assert root.order_drafts is not None

    def test_idempotency_accessor(self, root):
        assert root.idempotency is not None

    def test_order_draft_service_accessor(self, root):
        from application.order_draft_service import OrderDraftService

        assert isinstance(root.order_draft_service, OrderDraftService)

    def test_quote_drafts_accessor(self, root):
        assert root.quote_drafts is not None

    def test_quote_draft_service_accessor(self, root):
        from application.quote_draft_service import QuoteDraftService

        assert isinstance(root.quote_draft_service, QuoteDraftService)

    def test_payment_provider_accessor(self, root):
        from infrastructure.providers.mercadopago.gateway import MercadoPagoGateway

        assert isinstance(root.payment_provider, MercadoPagoGateway)

    def test_payment_service_accessor(self, root):
        from application.payment_service import PaymentService

        assert isinstance(root.payment_service, PaymentService)

    def test_delivery_requests_accessor(self, root):
        assert root.delivery_requests is not None

    def test_delivery_request_service_accessor(self, root):
        from application.delivery_request_service import DeliveryRequestService

        assert isinstance(root.delivery_request_service, DeliveryRequestService)

    def test_connection_accessor_is_the_same_connection(self, root, conn):
        assert root.connection is conn

    def test_consent_service_accessor(self, root):
        from application.consent_service import ConsentService

        assert isinstance(root.consent_service, ConsentService)

    def test_consent_accessor_degrades_to_unavailable_without_customer_privacy_schema(self, root):
        import asyncio

        from infrastructure.erp_clients.unavailable_client import ErpClientUnavailableError

        with pytest.raises(ErpClientUnavailableError):
            asyncio.run(root.consent.anything())

    def test_loyalty_service_accessor(self, root):
        from application.loyalty_service import LoyaltyService

        assert isinstance(root.loyalty_service, LoyaltyService)

    def test_loyalty_accessor_degrades_to_unavailable_without_loyalty_snapshots_table(self, root):
        import asyncio

        from infrastructure.erp_clients.unavailable_client import ErpClientUnavailableError

        with pytest.raises(ErpClientUnavailableError):
            asyncio.run(root.loyalty.anything())

    def test_handoff_coordinator_accessor(self, root):
        from application.handoff_service import HandoffCoordinator

        assert isinstance(root.handoff_coordinator, HandoffCoordinator)

    def test_handoff_requests_accessor(self, root):
        assert root.handoff_requests is not None

    def test_staff_directory_accessor_degrades_to_unavailable_without_legacy_schema(self, root):
        import asyncio

        from infrastructure.erp_clients.unavailable_client import ErpClientUnavailableError

        with pytest.raises(ErpClientUnavailableError):
            asyncio.run(root.staff_directory.anything())

    def test_outbox_accessor(self, root):
        assert root.outbox is not None

    def test_outbound_message_service_accessor(self, root):
        from application.outbound_message_service import OutboundMessageService

        assert isinstance(root.outbound_message_service, OutboundMessageService)

    def test_outbound_dispatcher_accessor(self, root):
        from infrastructure.webhooks.outbound_dispatcher import OutboundDispatcher

        assert isinstance(root.outbound_dispatcher, OutboundDispatcher)

    def test_notification_service_accessor(self, root):
        from application.notification_service import NotificationService

        assert isinstance(root.notification_service, NotificationService)

    def test_diagnostics_service_accessor(self, root):
        from application.diagnostics_service import DiagnosticsService

        assert isinstance(root.diagnostics_service, DiagnosticsService)

    def test_erp_clients_degrade_to_unavailable_without_legacy_schema(self, root):
        import asyncio

        from infrastructure.erp_clients.unavailable_client import ErpClientUnavailableError

        for client in (root.customers, root.catalog, root.orders, root.quotes, root.payments, root.delivery):
            with pytest.raises(ErpClientUnavailableError):
                asyncio.run(client.anything())


class TestErpClientsWithRealLegacySchema:
    """A diferencia del resto de esta suite (`:memory:`, solo esquema
    WA-3), aquí se monta una base en ARCHIVO temporal con el esquema WA-3
    MÁS una tabla `clientes` legacy mínima — el escenario real que
    `main.py` sí tiene en producción (`ERP_DB_PATH` con el esquema legacy
    completo vía las 243 migraciones)."""

    def test_real_erp_bridge_is_built_when_legacy_schema_present(self, tmp_path):
        db_path = str(tmp_path / "erp_with_legacy.db")
        connection = sqlite3.connect(db_path)
        create_whatsapp_schema(connection)
        connection.execute(
            "CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT, activo INTEGER DEFAULT 1)"
        )
        connection.commit()

        root = WhatsAppCompositionRoot(connection)
        try:
            from infrastructure.erp_clients.erp_bridge_clients import (
                ErpBridgeCustomersApiClient,
                ErpBridgeStaffDirectoryApiClient,
            )

            assert isinstance(root.customers, ErpBridgeCustomersApiClient)
            assert isinstance(root.staff_directory, ErpBridgeStaffDirectoryApiClient)
        finally:
            root.customers._bridge.close()  # cierra la conexión propia que ERPBridge abrió
            connection.close()


class TestConsentClientWithRealCustomerPrivacySchema:
    """A diferencia de `root` (`:memory:`, solo esquema WA-3), aquí se
    monta `customer_consents` (CRM-9) real en la misma conexión — el
    escenario real que `main.py` sí tiene en producción."""

    def test_real_consent_client_is_built_when_schema_present(self, tmp_path):
        import sqlite3

        from backend.infrastructure.db.schema.customer_privacy_schema import (
            create_customer_privacy_schema,
        )

        db_path = str(tmp_path / "erp_with_consent.db")
        connection = sqlite3.connect(db_path)
        create_whatsapp_schema(connection)
        create_customer_privacy_schema(connection)
        connection.commit()

        root = WhatsAppCompositionRoot(connection)
        try:
            from infrastructure.erp_clients.consent_client import CustomerConsentApiClient

            assert isinstance(root.consent, CustomerConsentApiClient)
        finally:
            connection.close()


class TestLoyaltyClientWithRealLoyaltySnapshotsTable:
    def test_real_loyalty_client_is_built_when_table_present(self, tmp_path):
        import sqlite3

        db_path = str(tmp_path / "erp_with_loyalty.db")
        connection = sqlite3.connect(db_path)
        create_whatsapp_schema(connection)
        connection.execute(
            "CREATE TABLE loyalty_snapshots (id TEXT PRIMARY KEY, cliente_id TEXT UNIQUE, "
            "puntos_actuales INTEGER DEFAULT 0, nivel TEXT DEFAULT 'Bronce', visitas INTEGER DEFAULT 0)"
        )
        connection.commit()

        root = WhatsAppCompositionRoot(connection)
        try:
            from infrastructure.erp_clients.loyalty_client import LoyaltySnapshotApiClient

            assert isinstance(root.loyalty, LoyaltySnapshotApiClient)
        finally:
            connection.close()


class TestDependencyGraphValidator:
    def test_raises_when_a_required_service_is_missing(self, conn):
        root = WhatsAppCompositionRoot(conn)
        root.registry._services.pop("whatsapp_message_repository")
        with pytest.raises(CompositionRootValidationError, match="whatsapp_message_repository"):
            validate_composition_root(root)

    def test_error_lists_every_missing_service(self, conn):
        root = WhatsAppCompositionRoot(conn)
        root.registry._services.pop("whatsapp_message_repository")
        root.registry._services.pop("whatsapp_identity_repository")
        with pytest.raises(CompositionRootValidationError) as exc_info:
            validate_composition_root(root)
        assert "whatsapp_message_repository" in str(exc_info.value)
        assert "whatsapp_identity_repository" in str(exc_info.value)
