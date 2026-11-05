"""SDLC-ARQ-PERM-001 — los casos de uso de escritura de Configuración se
autorizan en BACKEND, no sólo en `ConfiguracionPresenter._authorize`.

Regresión T0: hasta este ítem, un llamador que no pasara por el presentador
(script, API futura, otro módulo) escribía credenciales de integraciones o
creaba feature flags sin ninguna verificación. Estas pruebas construyen el
caso de uso SIN política y desactivan la sustitución permisiva de
`tests/conftest.py` (marca `unwired_fails_closed`): debe fallar cerrado y no
dejar rastro, ni en la BD ni en el almacén de secretos.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.application.configuracion.authorization import ConfiguracionActionAuthorizer
from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.application.use_cases.configuracion.feature_flag_management_use_cases import (
    CreateFeatureFlagUseCase,
)
from backend.application.use_cases.configuracion.integration_management_use_cases import (
    SetIntegrationInstanceCredentialUseCase,
)
from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.enums import IntegrationCategory
from backend.domain.settings.exceptions import (
    ConfigurationAuthorizationConfigurationError,
    ConfigurationPermissionDeniedError,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)
from tests.integration._born_clean_db import make_db


class _RecordingSecretStore:
    def __init__(self) -> None:
        self.set_calls: list[tuple[str, str]] = []

    def set_secret(self, name: str, value: str):
        self.set_calls.append((name, value))


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _seed_instance(conn) -> IntegrationInstance:
    """Siembra por repositorio (no por caso de uso, que ahora exige permiso)."""
    definition = IntegrationDefinition.create(
        code="mercadopago", name="MercadoPago", category=IntegrationCategory.PAYMENTS,
        required_credential_names=("mp_access_token",))
    SqliteIntegrationDefinitionRepository(conn).save(definition)
    instance = IntegrationInstance.create(definition_id=definition.id, name="MercadoPago prod")
    SqliteIntegrationInstanceRepository(conn).save(instance)
    conn.commit()
    return instance


@pytest.mark.unwired_fails_closed
def test_set_credential_without_policy_fails_closed_and_writes_nothing(conn):
    instance = _seed_instance(conn)
    secret_store = _RecordingSecretStore()

    with pytest.raises(ConfigurationAuthorizationConfigurationError):
        SetIntegrationInstanceCredentialUseCase(conn, secret_store).execute(
            instance_id=instance.id, credential_name="mp_access_token",
            secret_name="mp_access_token", secret_value="APP_USR-robado")

    assert secret_store.set_calls == []
    assert SqliteIntegrationInstanceRepository(conn).get(instance.id).credential_references == {}


@pytest.mark.unwired_fails_closed
def test_create_feature_flag_without_policy_fails_closed_and_writes_nothing(conn):
    with pytest.raises(ConfigurationAuthorizationConfigurationError):
        CreateFeatureFlagUseCase(conn).execute(code="flag_sin_permiso", name="Sin permiso")

    assert SqliteFeatureFlagRepository(conn).get_by_code("flag_sin_permiso") is None


def _session_authorizer(*grants):
    session = SimpleNamespace(user_id="u-admin", is_active=True,
                              tiene_permiso=lambda code: code in grants)
    return ConfiguracionActionAuthorizer.for_session(session)


def test_credential_denied_for_session_without_secret_permission(conn):
    """Quien puede editar integraciones pero no sus secretos no escribe el token."""
    instance = _seed_instance(conn)
    secret_store = _RecordingSecretStore()
    use_case = SetIntegrationInstanceCredentialUseCase(
        conn, secret_store, authorization=_session_authorizer(P.INTEGRACIONES_EDITAR))

    with pytest.raises(ConfigurationPermissionDeniedError):
        use_case.execute(instance_id=instance.id, credential_name="mp_access_token",
                         secret_name="mp_access_token", secret_value="APP_USR-robado")

    assert secret_store.set_calls == []
    assert SqliteIntegrationInstanceRepository(conn).get(instance.id).credential_references == {}


def test_credential_written_for_session_with_secret_permission(conn):
    instance = _seed_instance(conn)
    secret_store = _RecordingSecretStore()
    use_case = SetIntegrationInstanceCredentialUseCase(
        conn, secret_store, authorization=_session_authorizer(P.INTEGRACIONES_SECRETOS))

    use_case.execute(instance_id=instance.id, credential_name="mp_access_token",
                     secret_name="mp_access_token", secret_value="APP_USR-legitimo")

    assert secret_store.set_calls == [("mp_access_token", "APP_USR-legitimo")]
    assert SqliteIntegrationInstanceRepository(conn).get(instance.id).credential_references == {
        "mp_access_token": "mp_access_token"}
