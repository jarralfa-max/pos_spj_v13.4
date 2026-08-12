"""Shared fixtures for Customer Master integration tests (CRM-3)."""

import sqlite3

import pytest

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema


@pytest.fixture
def cust_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(conn)
    yield conn
    conn.close()
