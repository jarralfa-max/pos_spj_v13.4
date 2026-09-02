# tests/test_lifecycle.py — WA-4
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema
from bootstrap.lifecycle import start_composition_root, stop_composition_root


@pytest.fixture()
def db_path(tmp_path):
    path = str(tmp_path / "wa_test.db")
    conn = sqlite3.connect(path)
    create_whatsapp_schema(conn)
    conn.close()
    return path


class TestLifecycle:
    def test_start_returns_a_validated_root(self, db_path):
        root = start_composition_root(db_path)
        try:
            assert root.accounts is not None
            assert root.identities is not None
        finally:
            stop_composition_root(root)

    def test_stop_closes_the_connection(self, db_path):
        root = start_composition_root(db_path)
        stop_composition_root(root)
        conn = root.registry.get("whatsapp_db_connection")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_production_gate_blocks_start_when_secrets_missing(self, db_path, monkeypatch):
        monkeypatch.setattr("config.settings.is_production", lambda: True)
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        monkeypatch.setattr("config.settings.get_meta_phone_number_id", lambda: "present")
        monkeypatch.setattr("config.settings.get_verify_token", lambda: "present")
        monkeypatch.setattr("config.settings.get_app_secret", lambda: "present")
        monkeypatch.setattr("config.settings.get_internal_api_key", lambda: "present")
        monkeypatch.setattr("config.settings.MP_ACCESS_TOKEN", "", raising=False)
        with pytest.raises(RuntimeError):
            start_composition_root(db_path)

    def test_does_not_block_start_outside_production(self, db_path, monkeypatch):
        monkeypatch.setattr("config.settings.is_production", lambda: False)
        monkeypatch.setattr("config.settings.get_meta_access_token", lambda: "")
        root = start_composition_root(db_path)
        stop_composition_root(root)
