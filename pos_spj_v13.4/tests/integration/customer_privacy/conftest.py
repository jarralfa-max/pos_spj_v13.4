"""Shared fixtures for Customer Privacy integration tests (CRM-9)."""

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

_run_189 = importlib.import_module(
    "migrations.standalone.189_customer_privacy_bounded_context_schema").run


@pytest.fixture
def cp_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _run_189(conn)
    yield conn
    conn.close()


@pytest.fixture
def cp_and_customers_conn():
    """AnonymizeCustomerUseCase spans both bounded contexts — needs both
    schemas on the same connection."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _run_189(conn)
    create_customers_crm_schema(conn)
    yield conn
    conn.close()
