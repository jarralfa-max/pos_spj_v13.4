"""SET-19 — SqliteIntegrationHealthCheckRepository +
SqliteWebhookEndpointRepository against a real (in-memory) SQLite
born-clean schema (migration 219).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.integrations.entities.integration_definition import IntegrationDefinition
from backend.domain.integrations.entities.integration_health_check import IntegrationHealthCheck
from backend.domain.integrations.entities.integration_instance import IntegrationInstance
from backend.domain.integrations.entities.webhook_endpoint import WebhookEndpoint
from backend.domain.integrations.enums import IntegrationCategory, IntegrationHealthStatus, WebhookSignatureScheme
from backend.domain.integrations.policies.integration_health_policy import current_status
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
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _saved_instance(conn) -> IntegrationInstance:
    definition = IntegrationDefinition.create(
        code="whatsapp", name="WhatsApp Business", category=IntegrationCategory.MESSAGING,
    )
    SqliteIntegrationDefinitionRepository(conn).save(definition)
    instance = IntegrationInstance.create(definition_id=definition.id, name="Número principal")
    SqliteIntegrationInstanceRepository(conn).save(instance)
    conn.commit()
    return instance


class TestIntegrationHealthCheckRepository:
    def test_save_and_list_for_instance(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteIntegrationHealthCheckRepository(conn)

        repo.save(IntegrationHealthCheck.record(instance_id=instance.id, success=True, message="ok"))
        repo.save(IntegrationHealthCheck.record(instance_id=instance.id, success=False, message="timeout"))
        conn.commit()

        checks = repo.list_for_instance(instance.id)
        assert len(checks) == 2

    def test_composes_with_health_policy_end_to_end(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteIntegrationHealthCheckRepository(conn)

        repo.save(IntegrationHealthCheck.record(instance_id=instance.id, success=False, message="timeout"))
        conn.commit()

        checks = repo.list_for_instance(instance.id)
        assert current_status(checks) is IntegrationHealthStatus.DOWN

    def test_list_for_instance_respects_limit(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteIntegrationHealthCheckRepository(conn)
        for _ in range(5):
            repo.save(IntegrationHealthCheck.record(instance_id=instance.id, success=True))
        conn.commit()

        assert len(repo.list_for_instance(instance.id, limit=3)) == 3

    def test_list_for_instance_empty_when_none_recorded(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteIntegrationHealthCheckRepository(conn)
        assert repo.list_for_instance(instance.id) == []


class TestWebhookEndpointRepository:
    def test_save_get_roundtrip(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteWebhookEndpointRepository(conn)
        endpoint = WebhookEndpoint.create(
            instance_id=instance.id, code="whatsapp_inbound", path="/webhooks/whatsapp",
            signature_scheme=WebhookSignatureScheme.HMAC_SHA256_HEADER,
            signing_secret_reference="whatsapp/app_secret",
        )
        repo.save(endpoint)
        conn.commit()

        fetched = repo.get(endpoint.id)
        assert fetched.code == "WHATSAPP_INBOUND"
        assert fetched.signature_scheme is WebhookSignatureScheme.HMAC_SHA256_HEADER
        assert fetched.signing_secret_reference == "whatsapp/app_secret"

    def test_get_by_code(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteWebhookEndpointRepository(conn)
        endpoint = WebhookEndpoint.create(
            instance_id=instance.id, code="whatsapp_inbound", path="/webhooks/whatsapp",
        )
        repo.save(endpoint)
        conn.commit()
        assert repo.get_by_code("whatsapp_inbound").id == endpoint.id

    def test_code_is_unique(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteWebhookEndpointRepository(conn)
        repo.save(WebhookEndpoint.create(instance_id=instance.id, code="dup", path="/a"))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            repo.save(WebhookEndpoint.create(instance_id=instance.id, code="dup", path="/b"))
            conn.commit()
        conn.rollback()

    def test_mark_received_persists(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteWebhookEndpointRepository(conn)
        endpoint = WebhookEndpoint.create(instance_id=instance.id, code="whatsapp_inbound", path="/webhooks/whatsapp")
        repo.save(endpoint)
        conn.commit()

        endpoint.mark_received()
        repo.save(endpoint)
        conn.commit()

        assert repo.get(endpoint.id).last_received_at is not None

    def test_list_by_instance(self, conn):
        instance = _saved_instance(conn)
        repo = SqliteWebhookEndpointRepository(conn)
        repo.save(WebhookEndpoint.create(instance_id=instance.id, code="a", path="/a"))
        repo.save(WebhookEndpoint.create(instance_id=instance.id, code="b", path="/b"))
        conn.commit()

        assert len(repo.list_by_instance(instance.id)) == 2
