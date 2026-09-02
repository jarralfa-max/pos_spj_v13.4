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


class TestNotYetBuiltSubsystemsReportUnknown:
    def test_provider_gateway_is_unknown_not_healthy(self, root):
        results = run_all_checks(root)
        provider = next(r for r in results if r.name == "provider_gateway")
        assert provider.status == HealthStatus.UNKNOWN
        assert "WA-5" in provider.detail

    def test_inbox_worker_is_unknown(self, root):
        results = run_all_checks(root)
        inbox = next(r for r in results if r.name == "inbox_worker")
        assert inbox.status == HealthStatus.UNKNOWN


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
