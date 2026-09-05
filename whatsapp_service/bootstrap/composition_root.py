# bootstrap/composition_root.py — WA-4
"""
WhatsAppCompositionRoot (§8 del prompt maestro): construye las dependencias
reales del microservicio a partir de una única conexión SQLite ya abierta.

Cubre hoy lo que las fases anteriores ya construyeron: los repositorios
SQLite sobre las entidades de canal (WA-2 dominio + WA-3 esquema, incluido
el inbox de WA-6, drafts de WA-10/11, delivery de WA-13, handoff de WA-16,
outbox de WA-17), el `SecretStore` singleton (WA-1), el
`MetaCloudApiWhatsAppGateway` (WA-5), `WebhookProcessor`/`InboxWorker`
(WA-6), `ConversationEngine` (WA-7), `IntentResolutionService` (WA-8 —
capas 1-3 reales; capas 4-5 usan `NullIntentAIProvider` por defecto, sin
clasificador/LLM real conectado todavía), los 7 clientes ERP (WA-9/WA-16,
`domain/whatsapp/erp_ports.py` + `infrastructure/erp_clients/`), Consent
(WA-14), Fidelidad (WA-15), Handoff (WA-16) y Outbound Dispatcher (WA-17).
Lo que §8 pide y AÚN no existe se deja documentado explícitamente aquí —
no se inventan implementaciones falsas solo para completar la lista del
prompt maestro:

| Servicio (§8)          | Fase dueña | Estado                                                          |
|-------------------------|-----------|-------------------------------------------------------------------|
| WebhookAuthenticator        | WA-6       | parcial — la verificación de firma sigue en `webhook/whatsapp.py` (WA-1), no extraída a un servicio propio |
| TemplateRepository                   | futuro (§24) | pendiente — hoy `messaging/templates.py::TEMPLATES` es un diccionario Python |
| AgentRepository                        | futuro | pendiente — `HandoffCoordinator` (WA-16) asigna por teléfono de staff (`StaffDirectoryApiClient`), sin un directorio de agentes/turnos propio |

**Clientes ERP (WA-9) — degradación explícita, nunca silenciosa**: se
intenta construir un `ERPBridge` real a partir de la MISMA conexión que
recibió este root (vía `PRAGMA database_list`, nunca de una ruta global
desconectada) y se verifica que el esquema legacy (`clientes`) exista ahí.
Si cualquiera de los dos pasos falla (típico en tests, que solo montan el
esquema WA-3, sin `clientes`/`ventas`/etc.), los 6 clientes ERP se
registran como `UnavailableErpClient` — cualquier método invocado falla
explícito, nunca finge un resultado ni se omite en silencio del registro.

`SecretStoreGateway` de §8 ya existía desde WA-1
(`infrastructure/secrets/secret_store.py`) — este root reutiliza el MISMO
singleton de proceso (`config.settings.get_secret_store()`), nunca
construye un segundo `SecretStore`.
"""
from __future__ import annotations

import sqlite3

from bootstrap.service_registry import ServiceRegistry
from domain.whatsapp.repository_ports import (
    WhatsAppAccountRepository,
    WhatsAppConversationRepository,
    WhatsAppIdentityRepository,
    WhatsAppMessageRepository,
    WhatsAppNumberRepository,
    WhatsAppProviderConfigurationRepository,
)
from infrastructure.persistence.sqlite_account_repository import (
    SqliteWhatsAppAccountRepository,
    SqliteWhatsAppProviderConfigurationRepository,
)
from infrastructure.persistence.sqlite_conversation_repository import (
    SqliteWhatsAppConversationRepository,
)
from infrastructure.persistence.sqlite_delivery_request_repository import (
    SqliteWhatsAppDeliveryRequestRepository,
)
from infrastructure.persistence.sqlite_handoff_request_repository import (
    SqliteWhatsAppHandoffRequestRepository,
)
from infrastructure.persistence.sqlite_identity_repository import SqliteWhatsAppIdentityRepository
from infrastructure.persistence.sqlite_idempotency_repository import SqliteWhatsAppIdempotencyRepository
from infrastructure.persistence.sqlite_inbox_repository import SqliteWhatsAppInboxRepository
from infrastructure.persistence.sqlite_message_repository import SqliteWhatsAppMessageRepository
from infrastructure.persistence.sqlite_number_repository import SqliteWhatsAppNumberRepository
from infrastructure.persistence.sqlite_order_draft_repository import SqliteWhatsAppOrderDraftRepository
from infrastructure.persistence.sqlite_outbox_repository import SqliteWhatsAppOutboxRepository
from infrastructure.persistence.sqlite_quote_draft_repository import SqliteWhatsAppQuoteDraftRepository
from infrastructure.providers.meta_cloud_api.gateway import MetaCloudApiWhatsAppGateway
from infrastructure.providers.mercadopago.gateway import MercadoPagoGateway
from infrastructure.webhooks.inbox_worker import InboxWorker
from infrastructure.webhooks.outbound_dispatcher import OutboundDispatcher
from infrastructure.webhooks.webhook_processor import WebhookProcessor
from application.conversation_engine import ConversationEngine
from application.intent_resolution_service import IntentResolutionService
from application.order_draft_service import OrderDraftService
from application.quote_draft_service import QuoteDraftService
from application.payment_service import PaymentService
from application.delivery_request_service import DeliveryRequestService
from application.consent_service import ConsentService
from application.loyalty_service import LoyaltyService
from application.handoff_service import HandoffCoordinator
from application.outbound_message_service import OutboundMessageService
from application.notification_service import NotificationService
from application.diagnostics_service import DiagnosticsService
from infrastructure.erp_clients.unavailable_client import UnavailableErpClient

# Nombres canónicos de los servicios registrados — únicos en todo el árbol.
ACCOUNT_REPOSITORY = "whatsapp_account_repository"
PROVIDER_CONFIGURATION_REPOSITORY = "whatsapp_provider_configuration_repository"
NUMBER_REPOSITORY = "whatsapp_number_repository"
IDENTITY_REPOSITORY = "whatsapp_identity_repository"
CONVERSATION_REPOSITORY = "whatsapp_conversation_repository"
MESSAGE_REPOSITORY = "whatsapp_message_repository"
INBOX_REPOSITORY = "whatsapp_inbox_repository"
SECRET_STORE = "whatsapp_secret_store"
DB_CONNECTION = "whatsapp_db_connection"
PROVIDER_GATEWAY = "whatsapp_provider_gateway"
WEBHOOK_PROCESSOR = "whatsapp_webhook_processor"
INBOX_WORKER = "whatsapp_inbox_worker"
CONVERSATION_ENGINE = "whatsapp_conversation_engine"
INTENT_RESOLUTION_SERVICE = "whatsapp_intent_resolution_service"
CUSTOMERS_API_CLIENT = "whatsapp_customers_api_client"
CATALOG_API_CLIENT = "whatsapp_catalog_api_client"
ORDERS_API_CLIENT = "whatsapp_orders_api_client"
QUOTES_API_CLIENT = "whatsapp_quotes_api_client"
PAYMENTS_API_CLIENT = "whatsapp_payments_api_client"
DELIVERY_API_CLIENT = "whatsapp_delivery_api_client"
ORDER_DRAFT_REPOSITORY = "whatsapp_order_draft_repository"
IDEMPOTENCY_REPOSITORY = "whatsapp_idempotency_repository"
ORDER_DRAFT_SERVICE = "whatsapp_order_draft_service"
QUOTE_DRAFT_REPOSITORY = "whatsapp_quote_draft_repository"
QUOTE_DRAFT_SERVICE = "whatsapp_quote_draft_service"
PAYMENT_PROVIDER_GATEWAY = "whatsapp_payment_provider_gateway"
PAYMENT_SERVICE = "whatsapp_payment_service"
DELIVERY_REQUEST_REPOSITORY = "whatsapp_delivery_request_repository"
DELIVERY_REQUEST_SERVICE = "whatsapp_delivery_request_service"
CONSENT_API_CLIENT = "whatsapp_consent_api_client"
CONSENT_SERVICE = "whatsapp_consent_service"
LOYALTY_API_CLIENT = "whatsapp_loyalty_api_client"
LOYALTY_SERVICE = "whatsapp_loyalty_service"
STAFF_DIRECTORY_API_CLIENT = "whatsapp_staff_directory_api_client"
HANDOFF_REQUEST_REPOSITORY = "whatsapp_handoff_request_repository"
HANDOFF_COORDINATOR = "whatsapp_handoff_coordinator"
OUTBOX_REPOSITORY = "whatsapp_outbox_repository"
OUTBOUND_MESSAGE_SERVICE = "whatsapp_outbound_message_service"
OUTBOUND_DISPATCHER = "whatsapp_outbound_dispatcher"
NOTIFICATION_SERVICE = "whatsapp_notification_service"
DIAGNOSTICS_SERVICE = "whatsapp_diagnostics_service"

# Todo lo que este root SÍ construye hoy — dependency_graph_validator.py
# exige que las 41 estén presentes tras `_build()`.
REQUIRED_SERVICES = (
    DB_CONNECTION,
    SECRET_STORE,
    ACCOUNT_REPOSITORY,
    PROVIDER_CONFIGURATION_REPOSITORY,
    NUMBER_REPOSITORY,
    IDENTITY_REPOSITORY,
    CONVERSATION_REPOSITORY,
    MESSAGE_REPOSITORY,
    INBOX_REPOSITORY,
    PROVIDER_GATEWAY,
    WEBHOOK_PROCESSOR,
    INBOX_WORKER,
    CONVERSATION_ENGINE,
    INTENT_RESOLUTION_SERVICE,
    CUSTOMERS_API_CLIENT,
    CATALOG_API_CLIENT,
    ORDERS_API_CLIENT,
    QUOTES_API_CLIENT,
    PAYMENTS_API_CLIENT,
    DELIVERY_API_CLIENT,
    ORDER_DRAFT_REPOSITORY,
    IDEMPOTENCY_REPOSITORY,
    ORDER_DRAFT_SERVICE,
    QUOTE_DRAFT_REPOSITORY,
    QUOTE_DRAFT_SERVICE,
    PAYMENT_PROVIDER_GATEWAY,
    PAYMENT_SERVICE,
    DELIVERY_REQUEST_REPOSITORY,
    DELIVERY_REQUEST_SERVICE,
    CONSENT_API_CLIENT,
    CONSENT_SERVICE,
    LOYALTY_API_CLIENT,
    LOYALTY_SERVICE,
    STAFF_DIRECTORY_API_CLIENT,
    HANDOFF_REQUEST_REPOSITORY,
    HANDOFF_COORDINATOR,
    OUTBOX_REPOSITORY,
    OUTBOUND_MESSAGE_SERVICE,
    OUTBOUND_DISPATCHER,
    NOTIFICATION_SERVICE,
    DIAGNOSTICS_SERVICE,
)


class WhatsAppCompositionRoot:
    """Construye y registra las dependencias reales del microservicio.

    Recibe una conexión SQLite ya abierta — normalmente la misma `erp.db`
    que `main.py`/`ERPBridge` ya gestionan (una sola conexión compartida,
    no una por repositorio). El ciclo de vida de esa conexión (abrir/
    cerrar) es responsabilidad de `bootstrap/lifecycle.py`, no de este
    root.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.registry = ServiceRegistry()
        self._build()

    def _build(self) -> None:
        from config.settings import get_secret_store

        self.registry.register(DB_CONNECTION, self._conn)
        self.registry.register(SECRET_STORE, get_secret_store())
        self.registry.register(ACCOUNT_REPOSITORY, SqliteWhatsAppAccountRepository(self._conn))
        self.registry.register(
            PROVIDER_CONFIGURATION_REPOSITORY,
            SqliteWhatsAppProviderConfigurationRepository(self._conn),
        )
        self.registry.register(NUMBER_REPOSITORY, SqliteWhatsAppNumberRepository(self._conn))
        self.registry.register(IDENTITY_REPOSITORY, SqliteWhatsAppIdentityRepository(self._conn))
        self.registry.register(
            CONVERSATION_REPOSITORY, SqliteWhatsAppConversationRepository(self._conn)
        )
        self.registry.register(MESSAGE_REPOSITORY, SqliteWhatsAppMessageRepository(self._conn))
        self.registry.register(INBOX_REPOSITORY, SqliteWhatsAppInboxRepository(self._conn))
        self.registry.register(PROVIDER_GATEWAY, MetaCloudApiWhatsAppGateway())
        self.registry.register(WEBHOOK_PROCESSOR, WebhookProcessor(self))
        self.registry.register(INBOX_WORKER, InboxWorker(self))
        self.registry.register(CONVERSATION_ENGINE, ConversationEngine(self))
        self.registry.register(INTENT_RESOLUTION_SERVICE, IntentResolutionService())
        self.registry.register(ORDER_DRAFT_REPOSITORY, SqliteWhatsAppOrderDraftRepository(self._conn))
        self.registry.register(IDEMPOTENCY_REPOSITORY, SqliteWhatsAppIdempotencyRepository(self._conn))
        self.registry.register(QUOTE_DRAFT_REPOSITORY, SqliteWhatsAppQuoteDraftRepository(self._conn))
        self._build_erp_clients()
        self.registry.register(ORDER_DRAFT_SERVICE, OrderDraftService(self))
        self.registry.register(QUOTE_DRAFT_SERVICE, QuoteDraftService(self))
        self.registry.register(PAYMENT_PROVIDER_GATEWAY, MercadoPagoGateway())
        self.registry.register(PAYMENT_SERVICE, PaymentService(self))
        self.registry.register(
            DELIVERY_REQUEST_REPOSITORY, SqliteWhatsAppDeliveryRequestRepository(self._conn)
        )
        self.registry.register(DELIVERY_REQUEST_SERVICE, DeliveryRequestService(self))
        self._build_consent_client()
        self.registry.register(CONSENT_SERVICE, ConsentService(self))
        self._build_loyalty_client()
        self.registry.register(LOYALTY_SERVICE, LoyaltyService(self))
        self.registry.register(
            HANDOFF_REQUEST_REPOSITORY, SqliteWhatsAppHandoffRequestRepository(self._conn)
        )
        self.registry.register(HANDOFF_COORDINATOR, HandoffCoordinator(self))
        self.registry.register(OUTBOX_REPOSITORY, SqliteWhatsAppOutboxRepository(self._conn))
        self.registry.register(OUTBOUND_MESSAGE_SERVICE, OutboundMessageService(self))
        self.registry.register(OUTBOUND_DISPATCHER, OutboundDispatcher(self))
        self.registry.register(NOTIFICATION_SERVICE, NotificationService(self))
        self.registry.register(DIAGNOSTICS_SERVICE, DiagnosticsService(self))

    def _build_consent_client(self) -> None:
        """WA-14 — igual que `_build_erp_clients` (WA-9): degrada a
        `UnavailableErpClient` explícito si `customer_consents` (CRM-9) no
        existe en esta conexión (típico en tests que solo montan el
        esquema WA-3)."""
        try:
            self._conn.execute("SELECT 1 FROM customer_consents LIMIT 1")
            has_table = True
        except Exception:
            has_table = False

        if not has_table:
            self.registry.register(
                CONSENT_API_CLIENT,
                UnavailableErpClient(
                    CONSENT_API_CLIENT,
                    "sin tabla customer_consents (CRM-9) disponible en esta conexión",
                ),
            )
            return

        from infrastructure.erp_clients.consent_client import CustomerConsentApiClient

        self.registry.register(CONSENT_API_CLIENT, CustomerConsentApiClient(self._conn))

    def _build_loyalty_client(self) -> None:
        """WA-15 — mismo criterio de degradación explícita: sin
        `loyalty_snapshots` (Fidelidad) disponible en esta conexión, el
        cliente se registra como `UnavailableErpClient`."""
        try:
            self._conn.execute("SELECT 1 FROM loyalty_snapshots LIMIT 1")
            has_table = True
        except Exception:
            has_table = False

        if not has_table:
            self.registry.register(
                LOYALTY_API_CLIENT,
                UnavailableErpClient(
                    LOYALTY_API_CLIENT, "sin tabla loyalty_snapshots (Fidelidad) disponible en esta conexión",
                ),
            )
            return

        from infrastructure.erp_clients.loyalty_client import LoyaltySnapshotApiClient

        self.registry.register(LOYALTY_API_CLIENT, LoyaltySnapshotApiClient(self._conn))

    def _build_erp_clients(self) -> None:
        """WA-9 — intenta un `ERPBridge`/`ProductMatcher` reales contra la
        MISMA base que este root ya usa; degrada a `UnavailableErpClient`
        si el esquema legacy del ERP no está presente (ver docstring del
        módulo)."""
        bridge = self._try_build_erp_bridge()
        if bridge is None:
            reason = "sin ERPBridge real (esquema legacy del ERP no disponible en esta conexión)"
            for name in (
                CUSTOMERS_API_CLIENT, CATALOG_API_CLIENT, ORDERS_API_CLIENT,
                QUOTES_API_CLIENT, PAYMENTS_API_CLIENT, DELIVERY_API_CLIENT,
                STAFF_DIRECTORY_API_CLIENT,
            ):
                self.registry.register(name, UnavailableErpClient(name, reason))
            return

        from infrastructure.erp_clients.erp_bridge_clients import (
            ErpBridgeCustomersApiClient,
            ErpBridgeDeliveryApiClient,
            ErpBridgeOrdersApiClient,
            ErpBridgePaymentsApiClient,
            ErpBridgeQuotesApiClient,
            ErpBridgeStaffDirectoryApiClient,
            ProductMatcherCatalogApiClient,
        )
        from parser.product_matcher import ProductMatcher

        self.registry.register(CUSTOMERS_API_CLIENT, ErpBridgeCustomersApiClient(bridge))
        self.registry.register(
            CATALOG_API_CLIENT, ProductMatcherCatalogApiClient(ProductMatcher(bridge.db, sucursal_id=""))
        )
        self.registry.register(ORDERS_API_CLIENT, ErpBridgeOrdersApiClient(bridge))
        self.registry.register(QUOTES_API_CLIENT, ErpBridgeQuotesApiClient(bridge))
        self.registry.register(PAYMENTS_API_CLIENT, ErpBridgePaymentsApiClient(bridge))
        self.registry.register(DELIVERY_API_CLIENT, ErpBridgeDeliveryApiClient(bridge))
        self.registry.register(STAFF_DIRECTORY_API_CLIENT, ErpBridgeStaffDirectoryApiClient(bridge))

    def _try_build_erp_bridge(self):
        db_path = ""
        try:
            for row in self._conn.execute("PRAGMA database_list").fetchall():
                if row[1] == "main":
                    db_path = row[2] or ""
                    break
        except Exception:
            return None
        if not db_path:
            return None

        from erp.bridge import ERPBridge

        bridge = ERPBridge(db_path)
        try:
            bridge.db.execute("SELECT 1 FROM clientes LIMIT 1")
        except Exception:
            bridge.close()
            return None
        return bridge

    # ── Accesores tipados (evitan strings sueltos en los llamadores) ──────

    @property
    def accounts(self) -> WhatsAppAccountRepository:
        return self.registry.get(ACCOUNT_REPOSITORY)

    @property
    def provider_configurations(self) -> WhatsAppProviderConfigurationRepository:
        return self.registry.get(PROVIDER_CONFIGURATION_REPOSITORY)

    @property
    def numbers(self) -> WhatsAppNumberRepository:
        return self.registry.get(NUMBER_REPOSITORY)

    @property
    def identities(self) -> WhatsAppIdentityRepository:
        return self.registry.get(IDENTITY_REPOSITORY)

    @property
    def conversations(self) -> WhatsAppConversationRepository:
        return self.registry.get(CONVERSATION_REPOSITORY)

    @property
    def messages(self) -> WhatsAppMessageRepository:
        return self.registry.get(MESSAGE_REPOSITORY)

    @property
    def secret_store(self):
        return self.registry.get(SECRET_STORE)

    @property
    def provider_gateway(self) -> MetaCloudApiWhatsAppGateway:
        return self.registry.get(PROVIDER_GATEWAY)

    @property
    def inbox(self):
        return self.registry.get(INBOX_REPOSITORY)

    @property
    def webhook_processor(self) -> WebhookProcessor:
        return self.registry.get(WEBHOOK_PROCESSOR)

    @property
    def inbox_worker(self) -> InboxWorker:
        return self.registry.get(INBOX_WORKER)

    @property
    def conversation_engine(self) -> ConversationEngine:
        return self.registry.get(CONVERSATION_ENGINE)

    @property
    def intent_resolution_service(self) -> IntentResolutionService:
        return self.registry.get(INTENT_RESOLUTION_SERVICE)

    @property
    def customers(self):
        return self.registry.get(CUSTOMERS_API_CLIENT)

    @property
    def catalog(self):
        return self.registry.get(CATALOG_API_CLIENT)

    @property
    def orders(self):
        return self.registry.get(ORDERS_API_CLIENT)

    @property
    def quotes(self):
        return self.registry.get(QUOTES_API_CLIENT)

    @property
    def payments(self):
        return self.registry.get(PAYMENTS_API_CLIENT)

    @property
    def delivery(self):
        return self.registry.get(DELIVERY_API_CLIENT)

    @property
    def order_drafts(self):
        return self.registry.get(ORDER_DRAFT_REPOSITORY)

    @property
    def idempotency(self):
        return self.registry.get(IDEMPOTENCY_REPOSITORY)

    @property
    def order_draft_service(self) -> OrderDraftService:
        return self.registry.get(ORDER_DRAFT_SERVICE)

    @property
    def quote_drafts(self):
        return self.registry.get(QUOTE_DRAFT_REPOSITORY)

    @property
    def quote_draft_service(self) -> QuoteDraftService:
        return self.registry.get(QUOTE_DRAFT_SERVICE)

    @property
    def payment_provider(self) -> MercadoPagoGateway:
        return self.registry.get(PAYMENT_PROVIDER_GATEWAY)

    @property
    def payment_service(self) -> PaymentService:
        return self.registry.get(PAYMENT_SERVICE)

    @property
    def delivery_requests(self):
        return self.registry.get(DELIVERY_REQUEST_REPOSITORY)

    @property
    def delivery_request_service(self) -> DeliveryRequestService:
        return self.registry.get(DELIVERY_REQUEST_SERVICE)

    @property
    def connection(self):
        return self.registry.get(DB_CONNECTION)

    @property
    def consent(self):
        return self.registry.get(CONSENT_API_CLIENT)

    @property
    def consent_service(self) -> ConsentService:
        return self.registry.get(CONSENT_SERVICE)

    @property
    def loyalty(self):
        return self.registry.get(LOYALTY_API_CLIENT)

    @property
    def loyalty_service(self) -> LoyaltyService:
        return self.registry.get(LOYALTY_SERVICE)

    @property
    def staff_directory(self):
        return self.registry.get(STAFF_DIRECTORY_API_CLIENT)

    @property
    def handoff_requests(self):
        return self.registry.get(HANDOFF_REQUEST_REPOSITORY)

    @property
    def handoff_coordinator(self) -> HandoffCoordinator:
        return self.registry.get(HANDOFF_COORDINATOR)

    @property
    def outbox(self):
        return self.registry.get(OUTBOX_REPOSITORY)

    @property
    def outbound_message_service(self) -> OutboundMessageService:
        return self.registry.get(OUTBOUND_MESSAGE_SERVICE)

    @property
    def outbound_dispatcher(self) -> OutboundDispatcher:
        return self.registry.get(OUTBOUND_DISPATCHER)

    @property
    def notification_service(self) -> NotificationService:
        return self.registry.get(NOTIFICATION_SERVICE)

    @property
    def diagnostics_service(self) -> DiagnosticsService:
        return self.registry.get(DIAGNOSTICS_SERVICE)
