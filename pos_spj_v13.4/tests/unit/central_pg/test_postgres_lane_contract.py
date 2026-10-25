"""PostgreSQL central — lo verificable SIN servidor (arquitectura híbrida, Slice 3).

Lo que exige un PostgreSQL real (tipos efectivos, unicidad, JSONB, idempotencia
del carril) está en `tests/integration/central_pg/` y corre en el CI con un
PostgreSQL 16 de servicio. Aquí, las pruebas del carril usan una conexión
SIMULADA: prueban el orden de llamadas, no al motor.
"""

from __future__ import annotations

import importlib
import re
import sys
import types

import pytest

import migrations.engine as engine
from backend.infrastructure.db.database import (
    POSTGRES_DSN_ENV,
    DatabaseSettings,
    PostgresConfigurationError,
    create_connection_factory,
    redact_url,
)

URL = "postgresql://spj_api:s3cr3t@10.0.0.5:5432/spj"


# ── configuración ────────────────────────────────────────────────────────────
def test_password_never_shows_in_repr_or_messages():
    ajustes = DatabaseSettings.postgresql(URL)
    assert "s3cr3t" not in repr(ajustes) and "s3cr3t" not in str(ajustes)
    assert redact_url(URL) == "postgresql://spj_api:***@10.0.0.5:5432/spj"
    assert redact_url("postgresql://10.0.0.5/spj") == "postgresql://10.0.0.5/spj"


def test_settings_come_from_the_server_environment_only():
    with pytest.raises(PostgresConfigurationError, match=POSTGRES_DSN_ENV):
        DatabaseSettings.postgresql_from_env({})
    with pytest.raises(PostgresConfigurationError):
        DatabaseSettings.postgresql_from_env({POSTGRES_DSN_ENV: "  "})
    ajustes = DatabaseSettings.postgresql_from_env({POSTGRES_DSN_ENV: URL})
    assert ajustes.database_url == URL
    with pytest.raises((PostgresConfigurationError, ValueError)):
        DatabaseSettings.postgresql("sqlite:///x.db")


def test_missing_driver_is_a_clear_configuration_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    with pytest.raises(PostgresConfigurationError, match="psycopg"):
        create_connection_factory(DatabaseSettings.postgresql(URL))


def test_connections_are_transactional_and_bounded(monkeypatch):
    llamadas = []
    falso = types.SimpleNamespace(connect=lambda dsn, **kw: llamadas.append((dsn, kw)) or "c")
    monkeypatch.setitem(sys.modules, "psycopg", falso)
    fabrica = create_connection_factory(DatabaseSettings.postgresql(
        URL, connect_timeout_s=7, statement_timeout_ms=1500))
    assert fabrica() == "c"
    dsn, kw = llamadas[0]
    assert dsn == URL and kw["autocommit"] is False and kw["connect_timeout"] == 7
    assert kw["application_name"] == "spj-central"
    assert kw["options"] == "-c statement_timeout=1500"


def test_desktop_sqlite_path_is_unchanged(tmp_path):
    from backend.infrastructure.db.dialect import DatabaseDialect

    ajustes = DatabaseSettings(dialect=DatabaseDialect.SQLITE,
                               database_url=f"sqlite:///{tmp_path / 'spj.db'}")
    conexion = create_connection_factory(ajustes)()
    assert conexion.execute("SELECT 1").fetchone() == (1,)
    conexion.close()


# ── contrato del DDL central (§5.2) ──────────────────────────────────────────
def _ddl() -> list[tuple[str, str]]:
    salida = []
    for migracion in engine.PG_MIGRATIONS:
        modulo = importlib.import_module(migracion.module)
        salida += [(migracion.version, s) for s in modulo.DDL]
    return salida


def test_pg_lane_is_explicit_ordered_and_callable():
    versiones = [m.version for m in engine.PG_MIGRATIONS]
    assert versiones == sorted(versiones) and len(set(versiones)) == len(versiones)
    assert all(re.fullmatch(r"p\d{3}", v) for v in versiones)
    for migracion in engine.PG_MIGRATIONS:
        assert callable(importlib.import_module(migracion.module).run)


@pytest.mark.parametrize("prohibido", [
    r"\bREAL\b", r"\bFLOAT", r"\bDOUBLE\b", r"\bSERIAL\b", r"\bBIGSERIAL\b",
    r"\bIDENTITY\b", r"AUTOINCREMENT", r"gen_random_uuid", r"uuid_generate",
    r"\bTIMESTAMP\b(?!TZ)", r"\bMONEY\b",
])
def test_central_schema_never_uses_lossy_types_or_server_identities(prohibido):
    for version, sentencia in _ddl():
        assert not re.search(prohibido, sentencia, re.IGNORECASE), (version, prohibido)


def test_every_table_is_idempotent_and_keyed_by_uuid():
    for version, sentencia in _ddl():
        if "CREATE TABLE" in sentencia.upper():
            assert "CREATE TABLE IF NOT EXISTS" in sentencia, version
        if re.search(r"CREATE\s+(UNIQUE\s+)?INDEX", sentencia, re.IGNORECASE):
            assert "IF NOT EXISTS" in sentencia, version
        for columna in re.findall(r"^\s*(\w*_id|id)\s+(\w+)", sentencia, re.MULTILINE):
            assert columna[1].upper() == "UUID", (version, columna)


# ── carril con conexión SIMULADA ─────────────────────────────────────────────
class _Cursor:
    def __init__(self, conn):
        self.conn = conn
        self._fila = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.conn.sql.append(" ".join(sql.split())[:60])
        if self.conn.falla_en and self.conn.falla_en in sql:
            raise RuntimeError("falla simulada")
        if sql.startswith("SELECT 1 FROM schema_migrations"):
            self._fila = (1,) if params[0] in self.conn.hechas else None
        if sql.startswith("INSERT INTO schema_migrations"):
            self.conn.hechas.add(params[0])

    def fetchone(self):
        return self._fila


class _Conn:
    def __init__(self, hechas=(), falla_en=None):
        self.sql, self.hechas, self.falla_en = [], set(hechas), falla_en
        self.commits = self.rollbacks = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_lane_runs_pending_migrations_once_under_an_advisory_lock():
    conn = _Conn()
    assert engine.up_postgresql(conn) == len(engine.PG_MIGRATIONS)
    assert any("pg_advisory_lock" in s for s in conn.sql)
    assert conn.sql[-1].startswith("SELECT pg_advisory_unlock")
    assert engine.up_postgresql(conn) == 0     # ya aplicadas


def test_a_failing_migration_is_rolled_back_and_the_lock_released():
    conn = _Conn(falla_en="CREATE TABLE IF NOT EXISTS sync_inbox")
    with pytest.raises(engine.MigrationExecutionError):
        engine.up_postgresql(conn)
    assert "p001" not in conn.hechas
    assert conn.rollbacks >= 1
    assert conn.sql[-1].startswith("SELECT pg_advisory_unlock")
