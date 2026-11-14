"""SDLC-WA-002: reglas de `config/settings.py` para aceptar webhooks sin firma.

`get_app_env()` conserva su contrato. Lo nuevo es que un webhook sin firma
requiere un opt-in explícito, ignorado en producción y en estación instalada.
"""
from __future__ import annotations

import logging

import pytest

from backend.shared.app_paths import LAYOUT_INSTALLED, LAYOUT_SOURCE, AppPaths
from whatsapp_service.config import settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "APP_ENV",
        "ENVIRONMENT",
        "WA_ALLOW_UNSIGNED_WEBHOOKS",
        "MP_SIGNATURE_MAX_AGE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "_APP_PATHS", AppPaths(layout=LAYOUT_SOURCE))


def _installed(monkeypatch):
    monkeypatch.setattr(settings, "_APP_PATHS", AppPaths(layout=LAYOUT_INSTALLED))


@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", " Yes "])
def test_opt_in_values_allow_on_a_development_machine(monkeypatch, value):
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", value)
    assert settings.allow_unsigned_webhooks() is True


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "si", "2"])
def test_other_values_do_not_allow(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", value)
    assert settings.allow_unsigned_webhooks() is False


@pytest.mark.parametrize("app_env", ["production", "prod", "PRODUCTION"])
def test_opt_in_is_ignored_in_production(monkeypatch, app_env):
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setenv("APP_ENV", app_env)
    assert settings.allow_unsigned_webhooks() is False


def test_opt_in_follows_a_patched_is_production(monkeypatch):
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setattr(settings, "is_production", lambda: True)
    assert settings.allow_unsigned_webhooks() is False


def test_opt_in_is_ignored_on_an_installed_station(monkeypatch):
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    _installed(monkeypatch)
    assert settings.allow_unsigned_webhooks() is False


@pytest.mark.parametrize("secret_name", ["WA_APP_SECRET", "MP_WEBHOOK_SECRET"])
def test_rejection_without_opt_in_names_secret_and_how_to_enable(monkeypatch, secret_name):
    text = settings.unsigned_webhook_rejection(secret_name)
    assert secret_name in text
    assert "WA_ALLOW_UNSIGNED_WEBHOOKS=1" in text
    assert "se ignoró" not in text


def test_rejection_says_opt_in_was_ignored_by_production(monkeypatch):
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    monkeypatch.setenv("APP_ENV", "production")
    text = settings.unsigned_webhook_rejection("WA_APP_SECRET")
    assert "WA_APP_SECRET" in text
    assert "se ignoró por producción" in text


def test_rejection_says_opt_in_was_ignored_by_installed_station(monkeypatch):
    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    _installed(monkeypatch)
    text = settings.unsigned_webhook_rejection("MP_WEBHOOK_SECRET")
    assert "MP_WEBHOOK_SECRET" in text
    assert "se ignoró por estación instalada" in text


@pytest.mark.parametrize(
    "raw,expected_env",
    [("prd", "development"), ("staging", "development"), ("PRD ", "development")],
)
def test_unrecognized_env_is_reported_and_keeps_normalizing(monkeypatch, raw, expected_env):
    monkeypatch.setenv("APP_ENV", raw)
    status = settings.describe_webhook_security()
    assert settings.get_app_env() == expected_env
    assert status["env"] == expected_env
    assert status["unrecognized_env_value"] == raw.strip().lower()


@pytest.mark.parametrize(
    "raw", ["production", "prod", "test", "testing", "development", "dev"]
)
def test_recognized_env_is_not_reported(monkeypatch, raw):
    monkeypatch.setenv("APP_ENV", raw)
    assert settings.describe_webhook_security()["unrecognized_env_value"] is None


def test_environment_variable_is_also_read(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prd")
    assert settings.describe_webhook_security()["unrecognized_env_value"] == "prd"


def test_missing_env_is_not_reported_as_unrecognized():
    status = settings.describe_webhook_security()
    assert status["env"] == "development"
    assert status["unrecognized_env_value"] is None


def test_describe_reports_each_state(monkeypatch):
    assert settings.describe_webhook_security()["unsigned_allowed"] is False

    monkeypatch.setenv("WA_ALLOW_UNSIGNED_WEBHOOKS", "1")
    status = settings.describe_webhook_security()
    assert status["unsigned_allowed"] is True
    assert status["installed"] is False
    assert status["opt_in_ignored_reason"] is None

    _installed(monkeypatch)
    status = settings.describe_webhook_security()
    assert status["unsigned_allowed"] is False
    assert status["installed"] is True
    assert status["opt_in_ignored_reason"] == "estación instalada"


def test_describe_never_carries_a_secret_value(monkeypatch):
    monkeypatch.setattr(settings, "get_app_secret", lambda: "super-secret-value")
    monkeypatch.setattr(settings, "get_mp_webhook_secret", lambda: "super-secret-value")
    assert "super-secret-value" not in repr(settings.describe_webhook_security())


def test_mp_signature_window_defaults_to_300():
    assert settings.get_mp_signature_max_age_seconds() == 300


def test_mp_signature_window_is_read_on_each_call(monkeypatch):
    monkeypatch.setenv("MP_SIGNATURE_MAX_AGE_SECONDS", "1200")
    assert settings.get_mp_signature_max_age_seconds() == 1200
    monkeypatch.setenv("MP_SIGNATURE_MAX_AGE_SECONDS", "60")
    assert settings.get_mp_signature_max_age_seconds() == 60


@pytest.mark.parametrize("value", ["abc", "12.5", "0", "-1"])
def test_mp_signature_window_invalid_value_falls_back_with_warning(monkeypatch, caplog, value):
    monkeypatch.setenv("MP_SIGNATURE_MAX_AGE_SECONDS", value)
    with caplog.at_level(logging.WARNING, logger="wa.settings"):
        assert settings.get_mp_signature_max_age_seconds() == 300
    assert "MP_SIGNATURE_MAX_AGE_SECONDS" in caplog.text
