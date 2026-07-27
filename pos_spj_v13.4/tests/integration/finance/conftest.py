"""Shared fixtures for finance bounded-context integration tests."""

import sqlite3
from datetime import date

import pytest

from backend.application.services.finance.finance_bootstrap import bootstrap_finance
from backend.infrastructure.db.schema.finance_schema import create_finance_schema


@pytest.fixture
def finance_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_finance_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def bootstrapped_conn(finance_conn):
    bootstrap_finance(finance_conn, today=date(2026, 7, 16))
    return finance_conn
