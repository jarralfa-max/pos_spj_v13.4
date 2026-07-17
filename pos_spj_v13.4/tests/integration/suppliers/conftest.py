"""Shared fixtures for supplier integration tests."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema


@pytest.fixture
def sup_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_supplier_schema(conn)
    yield conn
    conn.close()
