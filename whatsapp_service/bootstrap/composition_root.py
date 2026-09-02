# bootstrap/composition_root.py — WA-4
"""
WhatsAppCompositionRoot (§8 del prompt maestro): construye las dependencias
reales del microservicio a partir de una única conexión SQLite ya abierta.

Cubre hoy exactamente lo que las fases anteriores ya construyeron: los 6
repositorios SQLite sobre las entidades de canal (WA-2 dominio + WA-3
esquema), y el `SecretStore` singleton (WA-1). Lo que §8 pide y AÚN no
existe se deja documentado explícitamente aquí — no se inventan
implementaciones falsas solo para completar la lista del prompt maestro:

| Servicio (§8)          | Fase dueña | Estado                                                          |
|-------------------------|-----------|-------------------------------------------------------------------|
| ProviderGateway           | WA-5       | pendiente                                                         |
| WebhookAuthenticator        | WA-6       | pendiente — hoy `webhook/whatsapp.py` valida la firma inline        |
| WebhookProcessor              | WA-6       | pendiente — hoy `webhook/whatsapp.py` procesa el mensaje inline       |
| OutboxRepository                | WA-17      | tabla `whatsapp_outbox` existe (WA-3), sin repositorio propio todavía   |
| IdempotencyRepository              | WA-9/WA-17 | tabla `whatsapp_business_operation_idempotency` existe (WA-3), ídem      |
| TemplateRepository                   | futuro (§24) | pendiente — hoy `messaging/templates.py::TEMPLATES` es un diccionario Python |
| AgentRepository                        | WA-16      | pendiente                                                                |
| ERP API clients                          | WA-9       | pendiente — hoy `erp/gateways/*` son gateways directos a SQLite/HTTP        |
| IntentResolver                             | WA-8       | existe una versión legacy (`ai/intent_resolver.py`), no wireada aquí          |
| ConversationEngine                           | WA-7       | pendiente                                                                       |
| HandoffCoordinator                              | WA-16      | pendiente — hoy `middleware/handoff.py` es un servicio simple, no wireado aquí  |
| OutboundMessageDispatcher                          | WA-17      | pendiente                                                                          |

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
from infrastructure.persistence.sqlite_identity_repository import SqliteWhatsAppIdentityRepository
from infrastructure.persistence.sqlite_message_repository import SqliteWhatsAppMessageRepository
from infrastructure.persistence.sqlite_number_repository import SqliteWhatsAppNumberRepository

# Nombres canónicos de los servicios registrados — únicos en todo el árbol.
ACCOUNT_REPOSITORY = "whatsapp_account_repository"
PROVIDER_CONFIGURATION_REPOSITORY = "whatsapp_provider_configuration_repository"
NUMBER_REPOSITORY = "whatsapp_number_repository"
IDENTITY_REPOSITORY = "whatsapp_identity_repository"
CONVERSATION_REPOSITORY = "whatsapp_conversation_repository"
MESSAGE_REPOSITORY = "whatsapp_message_repository"
SECRET_STORE = "whatsapp_secret_store"
DB_CONNECTION = "whatsapp_db_connection"

# Todo lo que este root SÍ construye hoy — dependency_graph_validator.py
# exige que las 8 estén presentes tras `_build()`.
REQUIRED_SERVICES = (
    DB_CONNECTION,
    SECRET_STORE,
    ACCOUNT_REPOSITORY,
    PROVIDER_CONFIGURATION_REPOSITORY,
    NUMBER_REPOSITORY,
    IDENTITY_REPOSITORY,
    CONVERSATION_REPOSITORY,
    MESSAGE_REPOSITORY,
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
