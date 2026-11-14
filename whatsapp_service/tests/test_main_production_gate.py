"""WA-1: gate de arranque en producción —
`main.py::_assert_production_secrets_configured`.

Antes de WA-1 no existía ningún chequeo de arranque que abortara si el
microservicio arrancaba en modo producción sin `WA_APP_SECRET`,
`WA_INTERNAL_API_KEY`, etc. configurados (whatsapp_security_audit.md §2/S4).
El proyecto ya tenía este mismo patrón ("bloquear en producción si falta
configuración crítica") para escrituras SQLite
(`erp/bridge.py::_assert_sqlite_write_allowed`) — esta es su aplicación al
riesgo de secretos de webhook/auth.

Se extrajo como función standalone específicamente para poder testearla sin
levantar el FastAPI app/DB/migraciones completos (no se llama a `lifespan`).
"""
from __future__ import annotations

import logging

import pytest

import whatsapp_service.main as wa_main

ALL_GETTERS = (
    "get_meta_access_token",
    "get_meta_phone_number_id",
    "get_verify_token",
    "get_app_secret",
    "get_internal_api_key",
)


def _configure_all_present(monkeypatch):
    for name in ALL_GETTERS:
        monkeypatch.setattr(f"whatsapp_service.config.settings.{name}", lambda: "present")
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "", raising=False)


def test_gate_is_noop_outside_production(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: False)
    monkeypatch.setattr("whatsapp_service.config.settings.get_meta_access_token", lambda: "")
    monkeypatch.setattr("whatsapp_service.config.settings.get_internal_api_key", lambda: "")
    # No debe lanzar aunque falten todos los secretos.
    wa_main._assert_production_secrets_configured()


def test_gate_passes_when_all_secrets_configured(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    wa_main._assert_production_secrets_configured()


@pytest.mark.parametrize("missing_getter", ALL_GETTERS)
def test_gate_raises_when_any_secret_missing_in_production(monkeypatch, missing_getter):
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr(f"whatsapp_service.config.settings.{missing_getter}", lambda: "")

    with pytest.raises(RuntimeError):
        wa_main._assert_production_secrets_configured()


def test_gate_does_not_require_mp_webhook_secret_when_mp_not_configured(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "", raising=False)
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")
    # MP_ACCESS_TOKEN vacío => MercadoPago no está en uso => no se exige su secreto.
    wa_main._assert_production_secrets_configured()


def test_gate_requires_mp_webhook_secret_when_mp_access_token_configured(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "mp-token-configured", raising=False)
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "")

    with pytest.raises(RuntimeError, match="MP_WEBHOOK_SECRET"):
        wa_main._assert_production_secrets_configured()


def test_gate_passes_when_mp_access_token_and_webhook_secret_both_configured(monkeypatch):
    monkeypatch.setattr("whatsapp_service.config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr("whatsapp_service.config.settings.MP_ACCESS_TOKEN", "mp-token-configured", raising=False)
    monkeypatch.setattr("whatsapp_service.config.settings.get_mp_webhook_secret", lambda: "present")
    wa_main._assert_production_secrets_configured()


# ── SDLC-WA-002: línea de estado de firma de webhooks ───────────────────────
def _status_records(caplog):
    return [r for r in caplog.records if "webhooks_sin_firma" in r.getMessage()]


def _describe(monkeypatch, **overrides):
    status = {
        "env": "development",
        "installed": False,
        "unsigned_allowed": False,
        "unrecognized_env_value": None,
        "opt_in_ignored_reason": None,
    }
    status.update(overrides)
    monkeypatch.setattr(
        "whatsapp_service.config.settings.describe_webhook_security", lambda: status
    )


def test_status_line_is_info_when_unsigned_is_blocked(monkeypatch, caplog):
    _describe(monkeypatch)
    with caplog.at_level(logging.INFO, logger="wa.main"):
        wa_main._log_webhook_security_status()
    records = _status_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    message = records[0].getMessage()
    assert "entorno=development" in message
    assert "instalado=no" in message
    assert "webhooks_sin_firma=bloqueado" in message
    assert len(caplog.records) == 1


def test_status_line_is_warning_when_unsigned_is_allowed(monkeypatch, caplog):
    _describe(monkeypatch, unsigned_allowed=True)
    with caplog.at_level(logging.INFO, logger="wa.main"):
        wa_main._log_webhook_security_status()
    records = _status_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "webhooks_sin_firma=permitido" in records[0].getMessage()


def test_status_line_reports_installed_station(monkeypatch, caplog):
    _describe(monkeypatch, installed=True)
    with caplog.at_level(logging.INFO, logger="wa.main"):
        wa_main._log_webhook_security_status()
    assert "instalado=sí" in _status_records(caplog)[0].getMessage()


def test_unrecognized_env_adds_a_separate_warning(monkeypatch, caplog):
    _describe(monkeypatch, unrecognized_env_value="prd")
    with caplog.at_level(logging.INFO, logger="wa.main"):
        wa_main._log_webhook_security_status()
    assert len(_status_records(caplog)) == 1
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "prd" in warnings[0]


def test_ignored_opt_in_adds_a_separate_warning(monkeypatch, caplog):
    _describe(monkeypatch, opt_in_ignored_reason="estación instalada")
    with caplog.at_level(logging.INFO, logger="wa.main"):
        wa_main._log_webhook_security_status()
    assert len(_status_records(caplog)) == 1
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "estación instalada" in warnings[0]
