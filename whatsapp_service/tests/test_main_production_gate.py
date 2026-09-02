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

import pytest

import main as wa_main

ALL_GETTERS = (
    "get_meta_access_token",
    "get_meta_phone_number_id",
    "get_verify_token",
    "get_app_secret",
    "get_internal_api_key",
)


def _configure_all_present(monkeypatch):
    for name in ALL_GETTERS:
        monkeypatch.setattr(f"config.settings.{name}", lambda: "present")
    monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "", raising=False)


def test_gate_is_noop_outside_production(monkeypatch):
    monkeypatch.setattr("config.settings.is_production", lambda: False)
    monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
    monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "")
    # No debe lanzar aunque falten todos los secretos.
    wa_main._assert_production_secrets_configured()


def test_gate_passes_when_all_secrets_configured(monkeypatch):
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    wa_main._assert_production_secrets_configured()


@pytest.mark.parametrize("missing_getter", ALL_GETTERS)
def test_gate_raises_when_any_secret_missing_in_production(monkeypatch, missing_getter):
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr(f"config.settings.{missing_getter}", lambda: "")

    with pytest.raises(RuntimeError):
        wa_main._assert_production_secrets_configured()


def test_gate_does_not_require_mp_webhook_secret_when_mp_not_configured(monkeypatch):
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "", raising=False)
    monkeypatch.setattr("config.settings.get_mp_webhook_secret", lambda: "")
    # MP_ACCESS_TOKEN vacío => MercadoPago no está en uso => no se exige su secreto.
    wa_main._assert_production_secrets_configured()


def test_gate_requires_mp_webhook_secret_when_mp_access_token_configured(monkeypatch):
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "mp-token-configured", raising=False)
    monkeypatch.setattr("config.settings.get_mp_webhook_secret", lambda: "")

    with pytest.raises(RuntimeError, match="MP_WEBHOOK_SECRET"):
        wa_main._assert_production_secrets_configured()


def test_gate_passes_when_mp_access_token_and_webhook_secret_both_configured(monkeypatch):
    monkeypatch.setattr("config.settings.is_production", lambda: True)
    _configure_all_present(monkeypatch)
    monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "mp-token-configured", raising=False)
    monkeypatch.setattr("config.settings.get_mp_webhook_secret", lambda: "present")
    wa_main._assert_production_secrets_configured()
