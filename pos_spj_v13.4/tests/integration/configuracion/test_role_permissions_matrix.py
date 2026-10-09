"""Dar o quitar permisos a un rol (Configuración → Usuarios y Roles → Permisos).

Antes: `SaveRolePermissionsUseCase` envolvía un servicio borrado con `core/` y
no había forma de cambiar los permisos de un rol desde la aplicación.
"""

from __future__ import annotations

import importlib

import pytest

from backend.application.commands.settings_commands import SaveRolePermissionsCommand
from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.configuracion.permissions import ConfiguracionPermissions as P
from backend.application.security.permission_query_service import PermissionQueryService
from backend.application.security.role_permission_matrix import RolePermissionMatrixQuery
from backend.application.use_cases.save_role_permissions_use_case import (
    SaveRolePermissionsUseCase,
)
from backend.domain.settings.exceptions import (
    ConfigurationInvalidValueError,
    ConfigurationPermissionDeniedError,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

ADMIN = "01900000-0000-7000-8000-0000000000a1"
GERENTE = "01900000-0000-7000-8000-0000000000a2"
CAJERO = "01900000-0000-7000-8000-0000000000a3"
OWNER = "01900000-0000-7000-8000-0000000000aa"


class _Grants:
    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def has_permission(self, user_id, code):
        return user_id in self._allowed


@pytest.fixture
def conn():
    c = make_db()
    importlib.import_module("migrations.standalone.047_v13_schema").up(c)
    importlib.import_module("migrations.standalone.224_configuracion_security_schema").run(c)
    yield c
    c.close()


def _user(conn, rol: str) -> str:
    uid = new_uuid()
    branch = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
                 " VALUES (?,?,?,?,?,?,1)", (uid, rol, f"{rol}-{uid[-6:]}", "x", rol, branch))
    conn.commit()
    return uid


def _grant_row(conn, role_id, code):
    modulo, accion = code.split(".", 1)
    conn.execute("INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                 " VALUES (?,?,?,?,1)", (new_uuid(), role_id, modulo, accion))
    conn.commit()


def _save(conn, actor, role_id, changes, *, authorized=True):
    auth = ConfiguracionAuthorizationPolicy(_Grants({actor} if authorized else set()))
    return SaveRolePermissionsUseCase(conn, auth).execute(SaveRolePermissionsCommand(
        operation_id=new_uuid(), branch_id="b", user_id=actor, role_id=role_id,
        permissions=tuple({"module": c.split(".", 1)[0], "action": c.split(".", 1)[1],
                           "allowed": v} for c, v in changes.items())))


def _codes_of(conn, user_id):
    return PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(user_id)


def test_the_matrix_lists_the_whole_catalog_and_what_the_role_has(conn):
    _grant_row(conn, CAJERO, "POS.ver")
    query = RolePermissionMatrixQuery(conn)
    matrix = query.matrix(CAJERO)
    assert matrix.mode == "EDITABLE" and "POS.ver" in matrix.granted
    assert len(matrix.modules) == 35
    assert {m.label for m in matrix.modules} >= {"Punto de venta", "Configuración", "Fidelidad"}
    assert query.matrix(ADMIN).mode == "FULL_ACCESS"
    assert query.matrix(OWNER).mode == "GRANT_ONLY"


def test_the_owner_grants_and_revokes_and_it_applies_on_next_login(conn):
    owner, cajero = _user(conn, "system_owner"), _user(conn, "cajero")
    result = _save(conn, owner, CAJERO, {"CAJA.reembolso.autorizar": True})
    assert result.data["granted"] == ("CAJA.reembolso.autorizar",)
    assert "CAJA.REEMBOLSO.AUTORIZAR" in _codes_of(conn, cajero)
    _save(conn, owner, CAJERO, {"CAJA.reembolso.autorizar": False})
    assert "CAJA.REEMBOLSO.AUTORIZAR" not in _codes_of(conn, cajero)
    acciones = conn.execute("SELECT action, user_id FROM configuracion_audit_log"
                            " WHERE entity_type='role_permissions'").fetchall()
    assert [tuple(a) for a in acciones] == [("ACTUALIZAR_PERMISOS", owner)] * 2


def test_without_the_permission_nothing_changes(conn):
    with pytest.raises(ConfigurationPermissionDeniedError):
        _save(conn, _user(conn, "gerente"), CAJERO, {"POS.ver": True}, authorized=False)


def test_only_catalog_permissions_can_be_granted(conn):
    with pytest.raises(ConfigurationInvalidValueError):
        _save(conn, _user(conn, "system_owner"), CAJERO, {"INVENTADO.todo": True})


def test_nobody_grants_a_permission_they_do_not_have(conn):
    _grant_row(conn, GERENTE, P.ROLES_PERMISOS)
    _grant_row(conn, GERENTE, "POS.ver")
    gerente = _user(conn, "gerente")
    _save(conn, gerente, CAJERO, {"POS.ver": True})
    with pytest.raises(ConfigurationPermissionDeniedError, match="no tienes"):
        _save(conn, gerente, CAJERO, {"CAJA.reembolso.autorizar": True})


def test_the_owner_role_never_loses_a_permission(conn):
    _grant_row(conn, OWNER, "POS.ver")
    with pytest.raises(ConfigurationInvalidValueError, match="dueño"):
        _save(conn, _user(conn, "system_owner"), OWNER, {"POS.ver": False})


def test_an_admin_role_is_not_edited(conn):
    with pytest.raises(ConfigurationInvalidValueError, match="acceso total"):
        _save(conn, _user(conn, "system_owner"), ADMIN, {"POS.ver": True})


def test_nobody_locks_themselves_out_of_this_screen(conn):
    for code in (P.ROLES_PERMISOS, P.GENERAL_VIEW, "POS.ver"):
        _grant_row(conn, GERENTE, code)
    gerente = _user(conn, "gerente")
    with pytest.raises(ConfigurationInvalidValueError, match="propio rol"):
        _save(conn, gerente, GERENTE, {P.ROLES_PERMISOS: False})
    _save(conn, gerente, GERENTE, {"POS.ver": False})  # lo demás sí


def test_repeating_the_same_change_is_a_no_op(conn):
    owner = _user(conn, "system_owner")
    _save(conn, owner, CAJERO, {"POS.ver": True})
    assert _save(conn, owner, CAJERO, {"POS.ver": True}).message == "Sin cambios."


def test_migration_304_gives_the_owner_the_permission(conn):
    importlib.import_module("migrations.standalone.304_seed_role_permissions_permission").run(conn)
    assert "CONFIGURACION.rol.permisos" in RolePermissionMatrixQuery(conn).matrix(OWNER).granted
