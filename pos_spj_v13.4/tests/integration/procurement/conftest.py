"""Shared fixtures for procurement integration tests."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema


@pytest.fixture
def proc_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(conn)
    yield conn
    conn.close()
