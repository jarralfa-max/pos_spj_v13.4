"""Shared fixtures for HR integration tests."""

import sqlite3

import pytest

from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.infrastructure.db.schema.hr_schema import create_hr_schema


class _IntegrationPermissionChecker:
    """Composición de prueba: concede todo. Las pruebas de seguridad
    (auditoría HR-01) construyen la política con su propio verificador."""

    def has_permission(self, user_id, permission_code):
        return True


@pytest.fixture(autouse=True)
def compose_hr_authorization(monkeypatch):
    """La política de RR. HH. falla cerrada sin verificador (HR-01). Las pruebas
    funcionales instancian casos de uso directamente: su raíz de composición
    aporta un verificador explícito, igual que en Compras."""
    original_init = AuthorizationPolicy.__init__

    def configured_init(self, checker=None):
        original_init(self, checker or _IntegrationPermissionChecker())

    monkeypatch.setattr(AuthorizationPolicy, "__init__", configured_init)


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
