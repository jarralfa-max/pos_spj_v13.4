"""Shared fixtures for procurement integration tests."""

import sqlite3

import pytest

from backend.application.procurement.authorization import PurchaseAuthorizationPolicy
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema


class _IntegrationPermissionChecker:
    """Explicit test composition dependency; production never uses this checker."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


@pytest.fixture(autouse=True)
def compose_procurement_authorization(monkeypatch):
    """Keep functional integration tests explicit about their authenticated RBAC seam.

    Most older scenarios instantiate use cases directly. Their test composition root
    supplies an allow-all checker, while unit security tests exercise fail-closed
    construction without this fixture.
    """
    original_init = PurchaseAuthorizationPolicy.__init__

    def configured_init(self, checker=None):
        original_init(self, checker or _IntegrationPermissionChecker())

    monkeypatch.setattr(PurchaseAuthorizationPolicy, "__init__", configured_init)


@pytest.fixture
def proc_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(conn)
    yield conn
    conn.close()
