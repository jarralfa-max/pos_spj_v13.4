"""SDLC-ARQ-TERM-002 · migración 357 — el permiso de re-anclaje es otorgable y
está otorgado a quien ya tenía acceso total, y a nadie más."""
from __future__ import annotations

import importlib

import pytest

from backend.application.configuracion.permissions import (
    ALL_CONFIGURACION_PERMISSIONS,
    ConfiguracionPermissions,
)
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS
from tests.integration.configuracion._reanchor_support import build_template, copy_of

_M357 = "migrations.standalone.357_seed_installation_reanchor_permission"


@pytest.fixture(scope="module")
def template():
    conn = build_template()
    yield conn
    conn.close()


@pytest.fixture
def conn(template):
    copia = copy_of(template)
    yield copia
    copia.close()


def _concedido_a(conn) -> set[str]:
    return {str(r[0]) for r in conn.execute(
        "SELECT r.nombre FROM rol_permisos p JOIN roles r ON r.id = p.rol_id"
        " WHERE upper(p.modulo)='CONFIGURACION' AND p.accion='estacion.reanclar'"
        " AND p.permitido=1")}


def test_the_code_is_declared_and_published_in_the_catalog():
    assert ConfiguracionPermissions.ESTACION_REANCLAR == "CONFIGURACION.estacion.reanclar"
    assert ConfiguracionPermissions.ESTACION_REANCLAR in ALL_CONFIGURACION_PERMISSIONS
    assert "estacion.reanclar" in CANONICAL_MODULE_PERMISSIONS["CONFIGURACION"]


def test_only_the_full_access_roles_receive_it(conn):
    assert _concedido_a(conn) == {"system_owner", "admin"}


def test_running_it_again_adds_nothing(conn):
    antes = conn.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0]
    importlib.import_module(_M357).run(conn)
    importlib.import_module(_M357).run(conn)
    assert conn.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0] == antes


def test_it_is_registered_in_the_engine():
    from migrations.engine import MIGRATIONS

    assert any(m.version == "357" and m.module == _M357 for m in MIGRATIONS)
