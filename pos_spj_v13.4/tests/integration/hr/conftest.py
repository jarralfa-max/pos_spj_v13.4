"""Shared fixtures for HR integration tests."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.hr_schema import create_hr_schema


@pytest.fixture
def hr_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_hr_schema(conn)
    # minimal usuarios table for user↔employee link tests
    conn.execute(
        "CREATE TABLE usuarios (id TEXT PRIMARY KEY, usuario TEXT, activo INTEGER"
        " DEFAULT 1, personal_id TEXT)")
    yield conn
    conn.close()
