"""Shared fixtures for Customer Service (atención al cliente) integration
tests (CRM-7)."""

import importlib
import sqlite3

import pytest

_run_186 = importlib.import_module(
    "migrations.standalone.186_customer_service_bounded_context_schema").run


@pytest.fixture
def cs_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _run_186(conn)
    yield conn
    conn.close()
