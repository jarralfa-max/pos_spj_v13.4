"""SET-19 cutover — real CRUD for the "Integraciones" section
(Definitions/Instances/Credentials/Health/Webhooks). Against a real
(in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.integration_management_use_cases import (
    ChangeIntegrationDefinitionStatusUseCase,
    ChangeIntegrationInstanceStatusUseCase,
    ChangeWebhookEndpointStatusUseCase,
    CreateIntegrationDefinitionUseCase,
    CreateIntegrationInstanceUseCase,
    CreateWebhookEndpointUseCase,
    IntegrationDefinitionStatusAction,
    IntegrationInstanceStatusAction,
    RecordIntegrationHealthCheckUseCase,
    SetIntegrationInstanceCredentialUseCase,
    UpdateIntegrationDefinitionUseCase,
    UpdateIntegrationInstanceUseCase,
    WebhookEndpointStatusAction,
)
from backend.domain.integrations.enums import IntegrationCategory, WebhookSignatureScheme
from backend.domain.integrations.exceptions import (
    IntegrationDefinitionNotFoundError,
    IntegrationInstanceNotFoundError,
    WebhookEndpointNotFoundError,
)
from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)
from backend.infrastructure.db.repositories.integrations.webhook_endpoint_repository import (
    SqliteWebhookEndpointRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


class _FakeSecretStore:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str]] = []
        self._store: dict[str, str] = {}

    def set_secret(self, name: str, value: str):
        self.set_calls.append((name, value))
        self._store[name] = value


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _definition(conn, **overrides):
    kwargs = dict(
        code="mercadopago", name="MercadoPago", category=IntegrationCategory.PAYMENTS,
        required_credential_names=("mp_access_token",),
    )
    kwargs.update(overrides)
    return CreateIntegrationDefinitionUseCase(conn).execute(**kwargs)


def _instance(conn, definition_id, **overrides):
    kwargs = dict(definition_id=definition_id, name="MercadoPago prod")
    kwargs.update(overrides)
    return CreateIntegrationInstanceUseCase(conn).execute(**kwargs)


class TestIntegrationDefinitionUseCases:
    def test_create_persists(self, conn):
        definition = _definition(conn)
        assert SqliteIntegrationDefinitionRepository(conn).get(definition.id) is not None

    def test_update_persists(self, conn):
        definition = _definition(conn)
        updated = UpdateIntegrationDefinitionUseCase(conn).execute(
            definition_id=definition.id, name="MP", required_credential_names=("token",))
        assert updated.name == "MP"
        assert SqliteIntegrationDefinitionRepository(conn).get(definition.id).required_credential_names == ("token",)

    def test_update_unknown_raises(self, conn):
        with pytest.raises(IntegrationDefinitionNotFoundError):
            UpdateIntegrationDefinitionUseCase(conn).execute(definition_id=new_uuid(), name="X")

    def test_change_status_activate_deactivate(self, conn):
        definition = _definition(conn)
        use_case = ChangeIntegrationDefinitionStatusUseCase(conn)
        deactivated = use_case.execute(
            definition_id=definition.id, action=IntegrationDefinitionStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(
            definition_id=definition.id, action=IntegrationDefinitionStatusAction.ACTIVATE)
        assert activated.active is True


class TestIntegrationInstanceUseCases:
    def test_create_persists(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        assert SqliteIntegrationInstanceRepository(conn).get(instance.id) is not None

    def test_update_persists(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        updated = UpdateIntegrationInstanceUseCase(conn).execute(
            instance_id=instance.id, name="Nuevo nombre", config={"region": "mx"})
        assert updated.name == "Nuevo nombre"
        assert SqliteIntegrationInstanceRepository(conn).get(instance.id).config == {"region": "mx"}

    def test_update_unknown_raises(self, conn):
        with pytest.raises(IntegrationInstanceNotFoundError):
            UpdateIntegrationInstanceUseCase(conn).execute(instance_id=new_uuid(), name="X")

    def test_change_status_activate_deactivate(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        use_case = ChangeIntegrationInstanceStatusUseCase(conn)
        deactivated = use_case.execute(
            instance_id=instance.id, action=IntegrationInstanceStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(
            instance_id=instance.id, action=IntegrationInstanceStatusAction.ACTIVATE)
        assert activated.active is True


class TestSetIntegrationInstanceCredentialUseCase:
    def test_writes_the_secret_and_the_reference_when_a_value_is_given(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        secret_store = _FakeSecretStore()

        updated = SetIntegrationInstanceCredentialUseCase(conn, secret_store).execute(
            instance_id=instance.id, credential_name="mp_access_token", secret_name="mp_access_token",
            secret_value="APP_USR-real-token",
        )

        assert secret_store.set_calls == [("mp_access_token", "APP_USR-real-token")]
        assert updated.credential_references == {"mp_access_token": "mp_access_token"}
        assert SqliteIntegrationInstanceRepository(conn).get(instance.id).credential_references == {
            "mp_access_token": "mp_access_token",
        }

    def test_only_repoints_the_reference_when_no_value_is_given(self, conn):
        """Blank value = keep the existing stored secret, just
        confirm/repoint the reference — mirrors
        `PaymentProviderSettingsService.save_mercado_pago_settings()`'s
        own "blank means don't touch" contract."""
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        secret_store = _FakeSecretStore()

        SetIntegrationInstanceCredentialUseCase(conn, secret_store).execute(
            instance_id=instance.id, credential_name="mp_access_token", secret_name="other_secret_name",
            secret_value=None,
        )

        assert secret_store.set_calls == []
        assert SqliteIntegrationInstanceRepository(conn).get(instance.id).credential_references == {
            "mp_access_token": "other_secret_name",
        }

    def test_unknown_instance_raises(self, conn):
        with pytest.raises(IntegrationInstanceNotFoundError):
            SetIntegrationInstanceCredentialUseCase(conn, _FakeSecretStore()).execute(
                instance_id=new_uuid(), credential_name="x", secret_name="x")


class TestWebhookEndpointUseCases:
    def test_create_persists(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        endpoint = CreateWebhookEndpointUseCase(conn).execute(
            instance_id=instance.id, code="MP_WEBHOOK", path="/webhooks/mercadopago",
            signature_scheme=WebhookSignatureScheme.MERCADOPAGO_TS_V1,
            signing_secret_reference="mp_webhook_secret",
        )
        assert SqliteWebhookEndpointRepository(conn).get(endpoint.id) is not None

    def test_change_status_activate_deactivate(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        endpoint = CreateWebhookEndpointUseCase(conn).execute(
            instance_id=instance.id, code="MP_WEBHOOK", path="/webhooks/mercadopago")
        use_case = ChangeWebhookEndpointStatusUseCase(conn)
        deactivated = use_case.execute(endpoint_id=endpoint.id, action=WebhookEndpointStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(endpoint_id=endpoint.id, action=WebhookEndpointStatusAction.ACTIVATE)
        assert activated.active is True

    def test_unknown_endpoint_raises(self, conn):
        with pytest.raises(WebhookEndpointNotFoundError):
            ChangeWebhookEndpointStatusUseCase(conn).execute(
                endpoint_id=new_uuid(), action=WebhookEndpointStatusAction.ACTIVATE)


class TestRecordIntegrationHealthCheckUseCase:
    def test_records_a_real_check(self, conn):
        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        check = RecordIntegrationHealthCheckUseCase(conn).execute(
            instance_id=instance.id, success=True, message="OK")
        assert check.success is True
        assert check.message == "OK"

    def test_health_status_reflects_recorded_checks(self, conn):
        from backend.domain.integrations.policies.integration_health_policy import current_status
        from backend.infrastructure.db.repositories.integrations.integration_health_check_repository import (
            SqliteIntegrationHealthCheckRepository,
        )

        definition = _definition(conn)
        instance = _instance(conn, definition.id)
        RecordIntegrationHealthCheckUseCase(conn).execute(instance_id=instance.id, success=False, message="Down")

        checks = SqliteIntegrationHealthCheckRepository(conn).list_for_instance(instance.id)
        assert current_status(checks).value == "DOWN"
