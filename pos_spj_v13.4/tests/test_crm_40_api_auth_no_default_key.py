"""CRM-40 (Fase 6, Autenticación) — the REST gateway's API key check must
never fall back to a known default value. Unconfigured server => 503 for
every request, never a guessable "dev-only" key that doubles as a
backdoor if a real deployment forgets to configure one."""
from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from api.auth import _get_configured_key, verify_api_key


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("ERP_API_KEY", raising=False)


class TestGetConfiguredKey:
    def test_none_when_nothing_configured(self):
        assert _get_configured_key(db=None) is None

    def test_reads_from_env_var(self, monkeypatch):
        monkeypatch.setenv("ERP_API_KEY", "real-secret-key")
        assert _get_configured_key(db=None) == "real-secret-key"

    def test_reads_from_db_when_env_absent(self):
        class _FakeRow:
            def __getitem__(self, i):
                return "db-secret-key"

        class _FakeDB:
            def execute(self, *a, **k):
                class _Cursor:
                    def fetchone(self_inner):
                        return _FakeRow()
                return _Cursor()

        assert _get_configured_key(db=_FakeDB()) == "db-secret-key"

    def test_env_var_takes_priority_over_db(self, monkeypatch):
        monkeypatch.setenv("ERP_API_KEY", "env-key")

        class _FakeDB:
            def execute(self, *a, **k):
                raise AssertionError("no debió consultar la BD si ENV ya tiene valor")

        assert _get_configured_key(db=_FakeDB()) == "env-key"


class TestVerifyApiKeyFailsClosed:
    def test_missing_header_denies(self):
        with pytest.raises(HTTPException) as exc:
            verify_api_key(api_key="", db=None)
        assert exc.value.status_code == 401

    def test_unconfigured_server_denies_every_request(self):
        """The core CRM-40 fix: previously this fell through to a
        hardcoded default and would have ACCEPTED "dev-only-change-in-production"."""
        with pytest.raises(HTTPException) as exc:
            verify_api_key(api_key="dev-only-change-in-production", db=None)
        assert exc.value.status_code == 503

    def test_unconfigured_server_denies_even_correct_looking_key(self):
        with pytest.raises(HTTPException) as exc:
            verify_api_key(api_key="anything-at-all", db=None)
        assert exc.value.status_code == 503

    def test_wrong_key_denies_when_configured(self, monkeypatch):
        monkeypatch.setenv("ERP_API_KEY", "the-real-key")
        with pytest.raises(HTTPException) as exc:
            verify_api_key(api_key="wrong-key", db=None)
        assert exc.value.status_code == 401

    def test_correct_key_allows_when_configured(self, monkeypatch):
        monkeypatch.setenv("ERP_API_KEY", "the-real-key")
        result = verify_api_key(api_key="the-real-key", db=None)
        assert result == "the-real-key"
