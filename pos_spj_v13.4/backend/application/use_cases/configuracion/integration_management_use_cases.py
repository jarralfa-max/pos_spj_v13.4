"""Use cases for the "Integraciones" section (Definitions/Instances/
Credentials/Health/Webhooks) — SET-19 cutover. Same shape as
`document_template_use_cases.py`/`customer_display_advertising_use_cases.py`:
thin orchestration over `backend/domain/integrations/` (SET-19),
construct/mutate the entity, persist.

`SetIntegrationInstanceCredentialUseCase` is the ONLY place in this file
that touches `SecretStoreGateway`, and only ever calls `set_secret()` —
never `get_secret()`. `SecretStoreGateway`'s own docstring is explicit
that UI-reachable code must never read a raw secret back; this use case
writes a value (when given) and always records the reference, mirroring
`PaymentProviderSettingsService.save_mercado_pago_settings()`'s own
"blank means don't touch the stored secret" contract.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_health_check import IntegrationHealthCheck
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.entities.webhook_endpoint import WebhookEndpoint
from backend.domain.integrations.enums import IntegrationCategory, WebhookSignatureScheme
from backend.domain.integrations.exceptions import (
    IntegrationDefinitionNotFoundError,
    IntegrationInstanceNotFoundError,
    WebhookEndpointNotFoundError,
)
from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_health_check_repository import (
    SqliteIntegrationHealthCheckRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)
from backend.infrastructure.db.repositories.integrations.webhook_endpoint_repository import (
    SqliteWebhookEndpointRepository,
)


class IntegrationDefinitionStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class IntegrationInstanceStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class WebhookEndpointStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


# ── IntegrationDefinition ────────────────────────────────────────────────────

class CreateIntegrationDefinitionUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._definitions = SqliteIntegrationDefinitionRepository(connection)

    def execute(
        self, *, code: str, name: str, category: IntegrationCategory | str,
        required_credential_names: tuple[str, ...] | list[str] = (),
    ) -> IntegrationDefinition:
        definition = IntegrationDefinition.create(
            code=code, name=name, category=IntegrationCategory(category),
            required_credential_names=required_credential_names,
        )
        self._definitions.save(definition)
        self._conn.commit()
        return definition


class UpdateIntegrationDefinitionUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._definitions = SqliteIntegrationDefinitionRepository(connection)

    def execute(
        self, *, definition_id: str, name: str, required_credential_names: tuple[str, ...] | list[str] = (),
    ) -> IntegrationDefinition:
        definition = self._definitions.get(definition_id)
        if definition is None:
            raise IntegrationDefinitionNotFoundError(f"Definición {definition_id} no encontrada")
        definition.update_details(name=name, required_credential_names=required_credential_names)
        self._definitions.save(definition)
        self._conn.commit()
        return definition


class ChangeIntegrationDefinitionStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._definitions = SqliteIntegrationDefinitionRepository(connection)

    def execute(self, *, definition_id: str, action: IntegrationDefinitionStatusAction) -> IntegrationDefinition:
        definition = self._definitions.get(definition_id)
        if definition is None:
            raise IntegrationDefinitionNotFoundError(f"Definición {definition_id} no encontrada")

        if action is IntegrationDefinitionStatusAction.ACTIVATE:
            definition.activate()
        elif action is IntegrationDefinitionStatusAction.DEACTIVATE:
            definition.deactivate()

        self._definitions.save(definition)
        self._conn.commit()
        return definition


# ── IntegrationInstance ──────────────────────────────────────────────────────

class CreateIntegrationInstanceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._instances = SqliteIntegrationInstanceRepository(connection)

    def execute(self, *, definition_id: str, name: str, config: dict | None = None) -> IntegrationInstance:
        instance = IntegrationInstance.create(definition_id=definition_id, name=name, config=config)
        self._instances.save(instance)
        self._conn.commit()
        return instance


class UpdateIntegrationInstanceUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._instances = SqliteIntegrationInstanceRepository(connection)

    def execute(self, *, instance_id: str, name: str, config: dict | None = None) -> IntegrationInstance:
        instance = self._instances.get(instance_id)
        if instance is None:
            raise IntegrationInstanceNotFoundError(f"Instancia {instance_id} no encontrada")
        instance.update_details(name=name, config=config)
        self._instances.save(instance)
        self._conn.commit()
        return instance


class ChangeIntegrationInstanceStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._instances = SqliteIntegrationInstanceRepository(connection)

    def execute(self, *, instance_id: str, action: IntegrationInstanceStatusAction) -> IntegrationInstance:
        instance = self._instances.get(instance_id)
        if instance is None:
            raise IntegrationInstanceNotFoundError(f"Instancia {instance_id} no encontrada")

        if action is IntegrationInstanceStatusAction.ACTIVATE:
            instance.activate()
        elif action is IntegrationInstanceStatusAction.DEACTIVATE:
            instance.deactivate()

        self._instances.save(instance)
        self._conn.commit()
        return instance


class SetIntegrationInstanceCredentialUseCase:
    def __init__(self, connection, secret_store) -> None:
        self._conn = connection
        self._instances = SqliteIntegrationInstanceRepository(connection)
        self._secret_store = secret_store

    def execute(
        self, *, instance_id: str, credential_name: str, secret_name: str, secret_value: str | None = None,
    ) -> IntegrationInstance:
        instance = self._instances.get(instance_id)
        if instance is None:
            raise IntegrationInstanceNotFoundError(f"Instancia {instance_id} no encontrada")
        if secret_value:
            self._secret_store.set_secret(secret_name, secret_value)
        instance.set_credential_reference(credential_name, secret_name)
        self._instances.save(instance)
        self._conn.commit()
        return instance


# ── WebhookEndpoint ──────────────────────────────────────────────────────────

class CreateWebhookEndpointUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._endpoints = SqliteWebhookEndpointRepository(connection)

    def execute(
        self, *, instance_id: str, code: str, path: str,
        signature_scheme: WebhookSignatureScheme | str = WebhookSignatureScheme.NONE,
        signing_secret_reference: str | None = None,
    ) -> WebhookEndpoint:
        endpoint = WebhookEndpoint.create(
            instance_id=instance_id, code=code, path=path,
            signature_scheme=WebhookSignatureScheme(signature_scheme),
            signing_secret_reference=signing_secret_reference,
        )
        self._endpoints.save(endpoint)
        self._conn.commit()
        return endpoint


class ChangeWebhookEndpointStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._endpoints = SqliteWebhookEndpointRepository(connection)

    def execute(self, *, endpoint_id: str, action: WebhookEndpointStatusAction) -> WebhookEndpoint:
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint is None:
            raise WebhookEndpointNotFoundError(f"Webhook {endpoint_id} no encontrado")

        if action is WebhookEndpointStatusAction.ACTIVATE:
            endpoint.activate()
        elif action is WebhookEndpointStatusAction.DEACTIVATE:
            endpoint.deactivate()

        self._endpoints.save(endpoint)
        self._conn.commit()
        return endpoint


# ── IntegrationHealthCheck ───────────────────────────────────────────────────

class RecordIntegrationHealthCheckUseCase:
    """Manual only — no live network probing. Same "pruebas" boundary
    SET-8/9/10 already established for hardware this repo can't safely
    call out to blind."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._checks = SqliteIntegrationHealthCheckRepository(connection)

    def execute(self, *, instance_id: str, success: bool, message: str = "") -> IntegrationHealthCheck:
        check = IntegrationHealthCheck.record(instance_id=instance_id, success=success, message=message)
        self._checks.save(check)
        self._conn.commit()
        return check
