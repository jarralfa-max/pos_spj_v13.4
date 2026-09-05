# tests/test_health_checks.py — WA-4 (§58 del prompt maestro)
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.composition_root import WhatsAppCompositionRoot
from bootstrap.health_checks import (
    HealthStatus,
    build_health_response,
    check_database,
    check_erp_api,
    check_inbox_queue,
    check_outbox_queue,
    check_provider_gateway,
    check_schema,
    check_secrets,
    overall_status,
    run_all_checks,
)


@pytest.fixture()
def root():
    connection = sqlite3.connect(":memory:")
    create_whatsapp_schema(connection)
    r = WhatsAppCompositionRoot(connection)
    yield r
    connection.close()


class TestIndividualChecks:
    def test_database_healthy_when_connection_works(self, root):
        assert check_database(root).status == HealthStatus.HEALTHY

    def test_schema_healthy_when_all_tables_present(self, root):
        assert check_schema(root).status == HealthStatus.HEALTHY

    def test_schema_unhealthy_when_a_table_is_missing(self, root):
        root.registry.get("whatsapp_db_connection").execute(
            "DROP TABLE whatsapp_dead_letter"
        )
        result = check_schema(root)
        assert result.status == HealthStatus.UNHEALTHY
        assert result.detail  # mensaje informativo, aunque sin nombres de ruta/tabla sensibles

    def test_secrets_degraded_outside_production_when_missing(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.is_production", lambda: False)
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "")
        monkeypatch.setattr("config.settings.get_verify_token", lambda: "")
        monkeypatch.setattr("config.settings.get_app_secret", lambda: "")
        monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "")
        result = check_secrets(root)
        assert result.status == HealthStatus.DEGRADED

    def test_secrets_unhealthy_in_production_when_missing(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.is_production", lambda: True)
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "present")
        monkeypatch.setattr("config.settings.get_verify_token", lambda: "present")
        monkeypatch.setattr("config.settings.get_app_secret", lambda: "present")
        monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "present")
        result = check_secrets(root)
        assert result.status == HealthStatus.UNHEALTHY

    def test_secrets_healthy_when_all_present(self, root, monkeypatch):
        for name in (
            "get_meta_access_token",
            "get_meta_phone_number_id",
            "get_verify_token",
            "get_app_secret",
            "get_internal_api_key",
        ):
            monkeypatch.setattr(f"config.settings.{name}", lambda: "present")
        assert check_secrets(root).status == HealthStatus.HEALTHY

    def test_detail_never_contains_a_secret_value(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.is_production", lambda: False)
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "")
        monkeypatch.setattr("config.settings.get_verify_token", lambda: "")
        monkeypatch.setattr("config.settings.get_app_secret", lambda: "super-secret-value")
        monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "")
        result = check_secrets(root)
        assert "super-secret-value" not in result.detail


class TestProviderGatewayCheck:
    """WA-5: `provider_gateway` pasó de placeholder UNKNOWN a un ping real
    contra la Graph API — ver `check_provider_gateway`."""

    def test_unknown_when_secrets_not_configured(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "")
        result = check_provider_gateway(root)
        assert result.status == HealthStatus.UNKNOWN
        assert "secrets" in result.detail

    def test_healthy_when_configured_and_ping_succeeds(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "token")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "phone-id")
        monkeypatch.setattr(
            "infrastructure.providers.meta_cloud_api.gateway.MetaCloudApiWhatsAppGateway.health_check",
            lambda self: True,
        )
        assert check_provider_gateway(root).status == HealthStatus.HEALTHY

    def test_unhealthy_when_configured_but_ping_fails(self, root, monkeypatch):
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "token")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "phone-id")
        monkeypatch.setattr(
            "infrastructure.providers.meta_cloud_api.gateway.MetaCloudApiWhatsAppGateway.health_check",
            lambda self: False,
        )
        result = check_provider_gateway(root)
        assert result.status == HealthStatus.UNHEALTHY

    def test_does_not_duplicate_secrets_severity(self, root, monkeypatch):
        """Fuera de producción, sin secretos, `check_secrets` ya reporta
        DEGRADED — `check_provider_gateway` no debe escalar a UNHEALTHY por
        la misma causa, solo reportar UNKNOWN."""
        monkeypatch.setattr("config.settings.is_production", lambda: False)
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "")
        assert check_provider_gateway(root).status != HealthStatus.UNHEALTHY


class TestInboxQueueCheck:
    """WA-6: `inbox_worker` pasó de placeholder UNKNOWN a profundidad/
    antigüedad real de `whatsapp_inbox` — ver `check_inbox_queue`."""

    def test_healthy_when_queue_empty(self, root):
        result = check_inbox_queue(root)
        assert result.status == HealthStatus.HEALTHY
        assert "0 pendientes" in result.detail

    def test_healthy_with_a_few_fresh_pending_jobs(self, root):
        from domain.whatsapp.entities.inbox_job import InboundMessageJob

        root.inbox.save(InboundMessageJob.create(message_id="msg-1"))
        assert check_inbox_queue(root).status == HealthStatus.HEALTHY

    def test_degraded_when_backlog_exceeds_threshold(self, root, monkeypatch):
        monkeypatch.setattr("bootstrap.health_checks._INBOX_DEGRADED_PENDING", 1)
        from domain.whatsapp.entities.inbox_job import InboundMessageJob

        root.inbox.save(InboundMessageJob.create(message_id="msg-1"))
        root.inbox.save(InboundMessageJob.create(message_id="msg-2"))
        assert check_inbox_queue(root).status == HealthStatus.DEGRADED

    def test_unhealthy_when_backlog_far_exceeds_threshold(self, root, monkeypatch):
        monkeypatch.setattr("bootstrap.health_checks._INBOX_UNHEALTHY_PENDING", 1)
        from domain.whatsapp.entities.inbox_job import InboundMessageJob

        root.inbox.save(InboundMessageJob.create(message_id="msg-1"))
        root.inbox.save(InboundMessageJob.create(message_id="msg-2"))
        assert check_inbox_queue(root).status == HealthStatus.UNHEALTHY

    def test_completed_jobs_do_not_count_toward_backlog(self, root):
        from domain.whatsapp.entities.inbox_job import InboundMessageJob

        job = InboundMessageJob.create(message_id="msg-1")
        job.claim()
        job.complete()
        root.inbox.save(job)
        result = check_inbox_queue(root)
        assert result.status == HealthStatus.HEALTHY
        assert "0 pendientes" in result.detail


class TestOutboxQueueCheck:
    """WA-17/WA-18: `outbox_worker` pasó de placeholder UNKNOWN ("pendiente
    — WA-17") a profundidad/antigüedad real de `whatsapp_outbox` — mismo
    criterio que `check_inbox_queue` (WA-6), en sentido saliente. Corregido
    junto con `check_erp_api` al notar, en el smoke test de WA-18, que
    ambos placeholders habían quedado obsoletos."""

    def test_healthy_when_queue_empty(self, root):
        result = check_outbox_queue(root)
        assert result.status == HealthStatus.HEALTHY
        assert "0 pendientes" in result.detail

    def test_healthy_with_a_few_fresh_pending_messages(self, root):
        from domain.whatsapp.entities.outbox_message import OutboxMessage

        root.outbox.save(OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola"))
        assert check_outbox_queue(root).status == HealthStatus.HEALTHY

    def test_degraded_when_backlog_exceeds_threshold(self, root, monkeypatch):
        monkeypatch.setattr("bootstrap.health_checks._OUTBOX_DEGRADED_PENDING", 1)
        from domain.whatsapp.entities.outbox_message import OutboxMessage

        root.outbox.save(OutboxMessage.enqueue_text(destination_phone="+525511111111", body="a"))
        root.outbox.save(OutboxMessage.enqueue_text(destination_phone="+525522222222", body="b"))
        assert check_outbox_queue(root).status == HealthStatus.DEGRADED

    def test_unhealthy_when_backlog_far_exceeds_threshold(self, root, monkeypatch):
        monkeypatch.setattr("bootstrap.health_checks._OUTBOX_UNHEALTHY_PENDING", 1)
        from domain.whatsapp.entities.outbox_message import OutboxMessage

        root.outbox.save(OutboxMessage.enqueue_text(destination_phone="+525511111111", body="a"))
        root.outbox.save(OutboxMessage.enqueue_text(destination_phone="+525522222222", body="b"))
        assert check_outbox_queue(root).status == HealthStatus.UNHEALTHY

    def test_sent_messages_do_not_count_toward_backlog(self, root):
        from domain.whatsapp.entities.outbox_message import OutboxMessage

        message = OutboxMessage.enqueue_text(destination_phone="+525512345678", body="Hola")
        message.claim()
        message.mark_sent()
        root.outbox.save(message)
        result = check_outbox_queue(root)
        assert result.status == HealthStatus.HEALTHY
        assert "0 pendientes" in result.detail


class TestErpApiCheck:
    def test_degraded_when_no_real_erp_bridge_available(self, root):
        """El fixture `root` solo monta el esquema WA-3 (sin `clientes`),
        así que WA-9 degrada a `UnavailableErpClient` — mismo escenario que
        `TestErpClientsWithRealLegacySchema` en `test_composition_root.py`."""
        result = check_erp_api(root)
        assert result.status == HealthStatus.DEGRADED

    def test_healthy_when_real_erp_bridge_is_built(self, tmp_path):
        connection = sqlite3.connect(str(tmp_path / "erp_with_legacy.db"))
        create_whatsapp_schema(connection)
        connection.execute(
            "CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT, activo INTEGER DEFAULT 1)"
        )
        connection.commit()
        root = WhatsAppCompositionRoot(connection)
        try:
            assert check_erp_api(root).status == HealthStatus.HEALTHY
        finally:
            root.customers._bridge.close()
            connection.close()


class TestOverallStatus:
    def test_empty_results_is_unknown(self):
        assert overall_status([]) == HealthStatus.UNKNOWN

    def test_unhealthy_beats_degraded(self):
        from bootstrap.health_checks import HealthCheckResult

        results = [
            HealthCheckResult("a", HealthStatus.DEGRADED),
            HealthCheckResult("b", HealthStatus.UNHEALTHY),
            HealthCheckResult("c", HealthStatus.HEALTHY),
        ]
        assert overall_status(results) == HealthStatus.UNHEALTHY

    def test_unknown_does_not_mask_unhealthy(self):
        from bootstrap.health_checks import HealthCheckResult

        results = [
            HealthCheckResult("a", HealthStatus.UNKNOWN),
            HealthCheckResult("b", HealthStatus.UNHEALTHY),
        ]
        assert overall_status(results) == HealthStatus.UNHEALTHY

    def test_all_unknown_is_unknown(self):
        from bootstrap.health_checks import HealthCheckResult

        results = [HealthCheckResult("a", HealthStatus.UNKNOWN)]
        assert overall_status(results) == HealthStatus.UNKNOWN


class TestBuildHealthResponse:
    def test_shape(self, root):
        response = build_health_response(root)
        assert "status" in response
        assert "checks" in response
        names = {c["name"] for c in response["checks"]}
        assert {"database", "schema", "secrets", "provider_gateway"}.issubset(names)
