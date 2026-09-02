"""SET-19 cutover — `resolve_mercadopago_secret_name()` and
`MercadoPagoService._get_token()`'s real cutover onto it. Against a real
(in-memory) SQLite born-clean schema. Designed conservatively — this is
the highest-risk surface (live payment credential resolution) this
refactor track has touched, so every test here is about NEVER breaking
the original hardcoded behavior.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)
from backend.infrastructure.integrations.mercadopago_credential_resolver import (
    resolve_mercadopago_secret_name,
)
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestResolveMercadopagoSecretName:
    def test_first_call_bootstraps_a_real_definition_and_instance(self, conn):
        secret_name = resolve_mercadopago_secret_name(conn)

        assert secret_name == "mp_access_token"
        definition = SqliteIntegrationDefinitionRepository(conn).get_by_code("MERCADOPAGO")
        assert definition is not None
        assert definition.required_credential_names == ("mp_access_token",)
        instances = SqliteIntegrationInstanceRepository(conn).list_by_definition(definition.id)
        assert len(instances) == 1
        assert instances[0].credential_references == {"mp_access_token": "mp_access_token"}

    def test_second_call_reuses_the_bootstrapped_rows_no_duplicates(self, conn):
        resolve_mercadopago_secret_name(conn)
        resolve_mercadopago_secret_name(conn)

        definition = SqliteIntegrationDefinitionRepository(conn).get_by_code("MERCADOPAGO")
        instances = SqliteIntegrationInstanceRepository(conn).list_by_definition(definition.id)
        assert len(instances) == 1

    def test_an_admin_repointed_reference_is_respected(self, conn):
        resolve_mercadopago_secret_name(conn)  # bootstrap
        definition = SqliteIntegrationDefinitionRepository(conn).get_by_code("MERCADOPAGO")
        instance_repo = SqliteIntegrationInstanceRepository(conn)
        instance = instance_repo.list_by_definition(definition.id)[0]
        instance.set_credential_reference("mp_access_token", "custom_secret_name")
        instance_repo.save(instance)
        conn.commit()

        assert resolve_mercadopago_secret_name(conn) == "custom_secret_name"

    def test_a_broken_connection_falls_back_to_the_hardcoded_constant_never_raises(self, conn):
        conn.close()

        secret_name = resolve_mercadopago_secret_name(conn)

        assert secret_name == "mp_access_token"  # PaymentProviderSettingsService.SECRET_NAME


class TestMercadoPagoServiceGetTokenCutover:
    def test_an_already_configured_token_is_found_through_the_bootstrapped_catalog(self, conn):
        class _FakeSecretStore:
            def get_secret(self, name):
                return "APP_USR-real-token" if name == "mp_access_token" else None

        with patch(
            "backend.security.secrets.default_secret_store.build_default_secret_store",
            return_value=_FakeSecretStore(),
        ):
            from services.mercado_pago_service import MercadoPagoService

            service = MercadoPagoService(conn=conn)

        assert service._token == "APP_USR-real-token"

    def test_no_token_configured_degrades_to_empty_string_same_as_before(self, conn):
        class _EmptySecretStore:
            def get_secret(self, name):
                return None

        with patch(
            "backend.security.secrets.default_secret_store.build_default_secret_store",
            return_value=_EmptySecretStore(),
        ):
            from services.mercado_pago_service import MercadoPagoService

            service = MercadoPagoService(conn=conn)

        assert service._token == ""

    def test_an_admin_repointed_reference_is_actually_used_by_the_real_service(self, conn):
        resolve_mercadopago_secret_name(conn)
        definition = SqliteIntegrationDefinitionRepository(conn).get_by_code("MERCADOPAGO")
        instance_repo = SqliteIntegrationInstanceRepository(conn)
        instance = instance_repo.list_by_definition(definition.id)[0]
        instance.set_credential_reference("mp_access_token", "sandbox_token")
        instance_repo.save(instance)
        conn.commit()

        class _FakeSecretStore:
            def get_secret(self, name):
                return {"sandbox_token": "APP_USR-sandbox-value"}.get(name)

        with patch(
            "backend.security.secrets.default_secret_store.build_default_secret_store",
            return_value=_FakeSecretStore(),
        ):
            from services.mercado_pago_service import MercadoPagoService

            service = MercadoPagoService(conn=conn)

        assert service._token == "APP_USR-sandbox-value"
