"""SET-19 — SqliteIntegrationDefinitionRepository +
SqliteIntegrationInstanceRepository against a real (in-memory) SQLite
born-clean schema (migration 219).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.enums import IntegrationCategory
from backend.domain.integrations.policies.credential_provisioning_policy import assert_credentials_satisfied
from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
    SqliteIntegrationDefinitionRepository,
)
from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
    SqliteIntegrationInstanceRepository,
)
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def definition_repo(conn):
    return SqliteIntegrationDefinitionRepository(conn)


@pytest.fixture
def instance_repo(conn):
    return SqliteIntegrationInstanceRepository(conn)


class TestIntegrationDefinitionRepository:
    def test_save_get_roundtrip_preserves_required_credentials(self, conn, definition_repo):
        definition = IntegrationDefinition.create(
            code="whatsapp", name="WhatsApp Business", category=IntegrationCategory.MESSAGING,
            required_credential_names=["app_secret", "access_token"],
        )
        definition_repo.save(definition)
        conn.commit()

        fetched = definition_repo.get(definition.id)
        assert fetched.code == "WHATSAPP"
        assert fetched.required_credential_names == ("app_secret", "access_token")

    def test_get_by_code(self, conn, definition_repo):
        definition = IntegrationDefinition.create(
            code="mercadopago", name="MercadoPago", category=IntegrationCategory.PAYMENTS,
        )
        definition_repo.save(definition)
        conn.commit()
        assert definition_repo.get_by_code("mercadopago").id == definition.id

    def test_code_is_unique(self, conn, definition_repo):
        definition_repo.save(IntegrationDefinition.create(
            code="whatsapp", name="A", category=IntegrationCategory.MESSAGING,
        ))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            definition_repo.save(IntegrationDefinition.create(
                code="whatsapp", name="B", category=IntegrationCategory.MESSAGING,
            ))
            conn.commit()
        conn.rollback()

    def test_list_active_excludes_inactive(self, conn, definition_repo):
        active = IntegrationDefinition.create(code="a", name="A", category=IntegrationCategory.OTHER)
        inactive = IntegrationDefinition.create(code="b", name="B", category=IntegrationCategory.OTHER)
        inactive.deactivate()
        definition_repo.save(active)
        definition_repo.save(inactive)
        conn.commit()

        codes = {d.code for d in definition_repo.list_active()}
        assert codes == {"A"}


class TestIntegrationInstanceRepository:
    def _saved_definition(self, conn, definition_repo) -> IntegrationDefinition:
        definition = IntegrationDefinition.create(
            code="whatsapp", name="WhatsApp Business", category=IntegrationCategory.MESSAGING,
            required_credential_names=["app_secret"],
        )
        definition_repo.save(definition)
        conn.commit()
        return definition

    def test_save_get_roundtrip_preserves_config_and_credentials(self, conn, definition_repo, instance_repo):
        definition = self._saved_definition(conn, definition_repo)
        instance = IntegrationInstance.create(
            definition_id=definition.id, name="Número principal", config={"phone_number_id": "123"},
        )
        instance.set_credential_reference("app_secret", "whatsapp/app_secret")
        instance_repo.save(instance)
        conn.commit()

        fetched = instance_repo.get(instance.id)
        assert fetched.config == {"phone_number_id": "123"}
        assert fetched.credential_references == {"app_secret": "whatsapp/app_secret"}

    def test_repository_round_trip_composes_with_credential_policy(self, conn, definition_repo, instance_repo):
        definition = self._saved_definition(conn, definition_repo)
        instance = IntegrationInstance.create(definition_id=definition.id, name="Número principal")
        instance.set_credential_reference("app_secret", "whatsapp/app_secret")
        instance_repo.save(instance)
        conn.commit()

        fetched_definition = definition_repo.get(definition.id)
        fetched_instance = instance_repo.get(instance.id)
        assert_credentials_satisfied(fetched_definition, fetched_instance)  # does not raise

    def test_list_by_definition(self, conn, definition_repo, instance_repo):
        definition = self._saved_definition(conn, definition_repo)
        other_definition = IntegrationDefinition.create(
            code="mercadopago", name="MercadoPago", category=IntegrationCategory.PAYMENTS,
        )
        definition_repo.save(other_definition)
        conn.commit()

        instance = IntegrationInstance.create(definition_id=definition.id, name="Instancia A")
        other_instance = IntegrationInstance.create(definition_id=other_definition.id, name="Instancia B")
        instance_repo.save(instance)
        instance_repo.save(other_instance)
        conn.commit()

        assert [i.id for i in instance_repo.list_by_definition(definition.id)] == [instance.id]

    def test_list_active_excludes_inactive(self, conn, definition_repo, instance_repo):
        definition = self._saved_definition(conn, definition_repo)
        active = IntegrationInstance.create(definition_id=definition.id, name="Activa")
        inactive = IntegrationInstance.create(definition_id=definition.id, name="Inactiva")
        inactive.deactivate()
        instance_repo.save(active)
        instance_repo.save(inactive)
        conn.commit()

        names = {i.name for i in instance_repo.list_active()}
        assert names == {"Activa"}
