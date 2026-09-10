"""DatabaseModuleProvider wired through a real CompositionRoot — not a
fake. Proves the registration resolves to the real, live connection pool
(`backend.infrastructure.db.connection.get_connection()`), that it's a working SQLite
connection (schema query succeeds), and that resolving it twice returns
the exact same object (SINGLETON, not a second connection to the file).
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.bootstrap.composition_root import CompositionRoot
from backend.bootstrap.wiring.database_wiring import DatabaseModuleProvider
from backend.infrastructure.db.connection import DatabaseWrapper, close_thread_connection, set_db_path


@pytest.fixture
def container(tmp_path):
    db_path = tmp_path / "wiring_test.db"
    set_db_path(str(db_path))
    close_thread_connection()  # avoid inheriting another test's thread-local connection
    root = CompositionRoot([DatabaseModuleProvider()])
    yield root.build()
    close_thread_connection()


def test_resolves_a_real_working_connection(container):
    conn = container.resolve(DatabaseWrapper)
    row = conn.execute("SELECT 1").fetchone()
    assert row[0] == 1


def test_resolving_twice_returns_the_same_singleton_instance(container):
    first = container.resolve(DatabaseWrapper)
    second = container.resolve(DatabaseWrapper)
    assert first is second


def test_connection_points_at_the_configured_db_path(container, tmp_path):
    conn = container.resolve(DatabaseWrapper)
    conn.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
    conn.commit()

    raw = sqlite3.connect(str(tmp_path / "wiring_test.db"))
    tables = raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    raw.close()
    assert ("probe",) in tables
