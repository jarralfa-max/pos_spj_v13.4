"""El secreto de firma de QR de Logística vive en el almacén de secretos (§46).

Re-auditoría 2026-10-04: estaba en texto plano en `configuraciones` y, si la
lectura fallaba, se generaba otro en silencio (lo que invalida toda etiqueta
impresa). Migración 300.
"""

from __future__ import annotations

import importlib

import pytest

from backend.application.logistics.composition import QR_SECRET_KEY, qr_signing_secret
from tests.integration._born_clean_db import make_db


class _Store:
    def __init__(self, initial=None, *, fail=False) -> None:
        self.values = dict(initial or {})
        self.fail = fail

    def get_secret(self, name):
        return self.values.get(name)

    def set_secret(self, name, value):
        if self.fail:
            raise RuntimeError("almacén no disponible")
        self.values[name] = value


_m300 = importlib.import_module("migrations.standalone.300_logistics_qr_secret_to_secret_store")


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _seed_plaintext(conn, value="ab" * 32):
    conn.execute(
        "INSERT INTO configuraciones (clave, valor, tipo, grupo, descripcion)"
        " VALUES (?, ?, 'texto', 'logistica', 'x')", (QR_SECRET_KEY, value))
    conn.commit()


def test_secret_is_created_once_in_the_store():
    store = _Store()

    first = qr_signing_secret(store)
    second = qr_signing_secret(store)

    assert first == second and len(first) == 32
    assert len(store.values[QR_SECRET_KEY]) == 64


def test_existing_store_secret_is_reused():
    store = _Store({QR_SECRET_KEY: "cd" * 32})

    assert qr_signing_secret(store) == bytes.fromhex("cd" * 32)


def test_unavailable_store_is_an_error_not_a_new_secret():
    with pytest.raises(RuntimeError):
        qr_signing_secret(_Store(fail=True))


def test_migration_drops_plaintext_when_no_label_was_printed(conn):
    _seed_plaintext(conn)
    store = _Store()

    _m300.run(conn, secret_store=store)

    assert conn.execute("SELECT 1 FROM configuraciones WHERE clave=?", (QR_SECRET_KEY,)).fetchone() is None
    assert store.values == {}


def test_migration_preserves_the_value_when_labels_exist(conn):
    _seed_plaintext(conn, "ef" * 32)
    conn.execute("CREATE TABLE IF NOT EXISTS logistics_container_labels (id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO logistics_container_labels (id) VALUES ('l1')")
    store = _Store()

    _m300.run(conn, secret_store=store)

    assert store.values[QR_SECRET_KEY] == "ef" * 32
    assert conn.execute("SELECT 1 FROM configuraciones WHERE clave=?", (QR_SECRET_KEY,)).fetchone() is None


def test_migration_fails_instead_of_losing_a_secret_printed_labels_depend_on(conn):
    _seed_plaintext(conn)
    conn.execute("CREATE TABLE IF NOT EXISTS logistics_container_labels (id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO logistics_container_labels (id) VALUES ('l1')")

    with pytest.raises(RuntimeError):
        _m300.run(conn, secret_store=_Store(fail=True))

    assert conn.execute("SELECT 1 FROM configuraciones WHERE clave=?", (QR_SECRET_KEY,)).fetchone()


def test_no_code_reads_the_secret_from_configuraciones():
    from pathlib import Path

    source = Path("backend/application/logistics/composition.py").read_text(encoding="utf-8")
    assert "FROM configuraciones" not in source
    assert "INTO configuraciones" not in source


def test_dead_configuration_keys_are_retired_and_nothing_reads_them(conn):
    """Migración 301: las claves sin lector se retiran, y siguen sin lector."""
    from pathlib import Path

    m301 = importlib.import_module("migrations.standalone.301_drop_dead_configuration_keys")
    conn.execute("INSERT OR IGNORE INTO configuraciones (clave, valor) VALUES ('sync_url', '')")
    conn.commit()

    m301.run(conn)

    marks = ",".join("?" for _ in m301.DEAD_KEYS)
    assert conn.execute(
        f"SELECT COUNT(*) FROM configuraciones WHERE clave IN ({marks})", m301.DEAD_KEYS).fetchone()[0] == 0
    for root in ("backend", "frontend"):
        for path in Path(root).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for key in m301.DEAD_KEYS:
                assert f"'{key}'" not in text and f'"{key}"' not in text, (path, key)
