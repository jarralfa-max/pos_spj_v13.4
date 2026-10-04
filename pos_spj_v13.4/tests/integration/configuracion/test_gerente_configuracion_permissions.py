"""Migración 302: `gerente` lee todas las secciones de Configuración y gestiona
dispositivos, asignaciones y rutas, pero nada de usuarios, secretos,
integraciones, flags ni plantillas (decisión del usuario, 2026-10-04)."""

from __future__ import annotations

import importlib

import pytest

from backend.application.configuracion.permissions import (
    ALL_CONFIGURACION_PERMISSIONS,
    ConfiguracionPermissions as P,
)
from backend.application.security.permission_query_service import PermissionQueryService
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.shared.ids import new_uuid
from frontend.desktop.modules.configuracion.navigation.configuracion_sidebar import CONFIGURACION_NAV
from tests.integration._born_clean_db import make_db

_m302 = importlib.import_module("migrations.standalone.302_seed_gerente_configuracion_permissions")


@pytest.fixture
def conn():
    connection = make_db()
    importlib.import_module("migrations.standalone.047_v13_schema").up(connection)
    yield connection
    connection.close()


def _gerente_codes(conn) -> frozenset[str]:
    branch = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    user_id = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
        " VALUES (?, 'G', 'gerente_t', 'x', 'gerente', ?, 1)", (user_id, branch))
    conn.commit()
    # El servicio devuelve los códigos normalizados a MAYÚSCULAS; la sesión
    # compara igual, así que la prueba también.
    return frozenset(code.upper() for code in PermissionQueryService(
        SqlitePermissionRepository(conn)).permission_codes_for_user(user_id, branch))


def test_snapshot_only_names_codes_that_exist():
    assert set(_m302.GERENTE_CODES) <= ALL_CONFIGURACION_PERMISSIONS


def test_gerente_reads_every_section_and_manages_devices(conn):
    _m302.run(conn)
    _m302.run(conn)  # idempotente

    codes = _gerente_codes(conn)

    assert {entry.permission.upper() for entry in CONFIGURACION_NAV} <= codes
    assert {c.upper() for c in (P.DISPOSITIVOS_CREAR, P.DISPOSITIVOS_EDITAR, P.DISPOSITIVOS_ASIGNAR,
                                P.DISPOSITIVOS_RUTAS_GESTIONAR)} <= codes


def test_gerente_gets_nothing_sensitive(conn):
    _m302.run(conn)

    codes = _gerente_codes(conn)

    for code in (P.USUARIOS_CREAR, P.USUARIOS_EDITAR, P.ROLES_EDITAR, P.INTEGRACIONES_SECRETOS,
                 P.INTEGRACIONES_ACTIVAR, P.FEATURE_FLAGS_ACTIVAR, P.DOCUMENTOS_PLANTILLA_ACTIVAR,
                 P.TEMA_ACTIVAR, P.DISPOSITIVOS_DESHABILITAR):
        assert code.upper() not in codes, code
