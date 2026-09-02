"""WA-1 §1: `SecretStore` — lectura de `configuraciones` con cache TTL.

Antes de esto, cada lectura de secreto reabría una conexión SQLite nueva
(sin caching) en cada llamada a `send_message`/webhook
(whatsapp_security_audit.md, Hallazgo 1).
"""
from __future__ import annotations

import sqlite3
import time

from infrastructure.secrets.secret_store import SecretStore


def _db_with_config(tmp_path, clave: str, valor: str) -> str:
    db_path = str(tmp_path / "erp.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    conn.execute("INSERT INTO configuraciones (clave, valor) VALUES (?, ?)", (clave, valor))
    conn.commit()
    conn.close()
    return db_path


def test_get_reads_from_db_first(tmp_path):
    db_path = _db_with_config(tmp_path, "wa_meta_token", "db-value")
    store = SecretStore(lambda: db_path)
    assert store.get("meta_token", "env-fallback") == "db-value"


def test_get_falls_back_to_env_when_db_has_no_row(tmp_path):
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    conn.commit()
    conn.close()

    store = SecretStore(lambda: db_path)
    assert store.get("meta_token", "env-fallback") == "env-fallback"


def test_get_falls_back_to_env_when_db_path_missing():
    store = SecretStore(lambda: "")
    assert store.get("meta_token", "env-fallback") == "env-fallback"


def test_get_caches_db_read_within_ttl(tmp_path):
    db_path = _db_with_config(tmp_path, "wa_meta_token", "first-value")
    store = SecretStore(lambda: db_path, ttl_seconds=60.0)

    assert store.get("meta_token") == "first-value"

    # Cambia el valor directamente en la BD sin pasar por la cache.
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE configuraciones SET valor='second-value' WHERE clave='wa_meta_token'")
    conn.commit()
    conn.close()

    # Dentro del TTL, sigue devolviendo el valor cacheado.
    assert store.get("meta_token") == "first-value"


def test_clear_cache_forces_fresh_read(tmp_path):
    db_path = _db_with_config(tmp_path, "wa_meta_token", "first-value")
    store = SecretStore(lambda: db_path, ttl_seconds=60.0)
    assert store.get("meta_token") == "first-value"

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE configuraciones SET valor='second-value' WHERE clave='wa_meta_token'")
    conn.commit()
    conn.close()

    store.clear_cache()
    assert store.get("meta_token") == "second-value"


def test_get_expires_cache_after_ttl(tmp_path):
    db_path = _db_with_config(tmp_path, "wa_meta_token", "first-value")
    store = SecretStore(lambda: db_path, ttl_seconds=0.05)
    assert store.get("meta_token") == "first-value"

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE configuraciones SET valor='second-value' WHERE clave='wa_meta_token'")
    conn.commit()
    conn.close()

    time.sleep(0.1)
    assert store.get("meta_token") == "second-value"


def test_mask_matches_credential_service_pattern():
    assert SecretStore.mask("EAAGabcdef1234567890XYZ") == "EAAG" + "*" * 15 + "0XYZ"
    assert SecretStore.mask("short") == "***"
    assert SecretStore.mask("") == "***"
