"""Excepciones de permiso por usuario (Usuarios y Roles → Usuarios → Permisos).

`usuario_permisos` y su evaluación existían; no había forma de escribirlas.
"""

from __future__ import annotations

import importlib
import os

import pytest

from backend.application.commands.settings_commands import SaveUserPermissionsCommand
from backend.application.configuracion.authorization import ConfiguracionAuthorizationPolicy
from backend.application.security.permission_query_service import PermissionQueryService
from backend.application.security.user_permission_matrix import UserPermissionMatrixQuery
from backend.application.use_cases.save_user_permissions_use_case import (
    SaveUserPermissionsUseCase,
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

CAJERO = "01900000-0000-7000-8000-0000000000a3"
GERENTE = "01900000-0000-7000-8000-0000000000a2"


class _Grants:
    def __init__(self, allowed) -> None:
        self._allowed = set(allowed)

    def has_permission(self, user_id, code):
        return user_id in self._allowed


@pytest.fixture
def conn():
    c = make_db()
    importlib.import_module("migrations.standalone.047_v13_schema").up(c)
    importlib.import_module("migrations.standalone.224_configuracion_security_schema").run(c)
    yield c
    c.close()


def _user(conn, rol):
    uid = new_uuid()
    branch = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()[0]
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id, activo)"
                 " VALUES (?,?,?,?,?,?,1)", (uid, rol, f"{rol}-{uid[-6:]}", "x", rol, branch))
    conn.commit()
    return uid


def _grant_role(conn, role_id, code):
    modulo, accion = code.split(".", 1)
    conn.execute("INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                 " VALUES (?,?,?,?,1)", (new_uuid(), role_id, modulo, accion))
    conn.commit()


def _save(conn, actor, target, changes, *, authorized=True):
    auth = ConfiguracionAuthorizationPolicy(_Grants({actor} if authorized else ()))
    return SaveUserPermissionsUseCase(conn, auth).execute(SaveUserPermissionsCommand(
        operation_id=new_uuid(), branch_id="b", user_id=actor, target_user_id=target,
        permissions=tuple({"module": c.split(".", 1)[0], "action": c.split(".", 1)[1],
                           "state": s} for c, s in changes.items())))


def _codes(conn, user_id):
    return PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(user_id)


def test_grant_deny_and_back_to_the_role(conn):
    _grant_role(conn, CAJERO, "POS.ver")
    owner, cajero = _user(conn, "system_owner"), _user(conn, "cajero")
    _save(conn, owner, cajero, {"CAJA.reembolso.autorizar": "GRANT", "POS.ver": "DENY"})
    codes = _codes(conn, cajero)
    assert "CAJA.REEMBOLSO.AUTORIZAR" in codes and "POS.VER" not in codes
    otro_cajero = _user(conn, "cajero")
    assert "POS.VER" in _codes(conn, otro_cajero)  # sólo a ESE usuario
    _save(conn, owner, cajero, {"CAJA.reembolso.autorizar": "INHERIT", "POS.ver": "INHERIT"})
    codes = _codes(conn, cajero)
    assert "CAJA.REEMBOLSO.AUTORIZAR" not in codes and "POS.VER" in codes
    assert conn.execute("SELECT COUNT(*) FROM usuario_permisos").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM configuracion_audit_log"
                        " WHERE entity_type='user_permissions'").fetchone()[0] == 2


def test_the_matrix_shows_role_value_and_exception_apart(conn):
    _grant_role(conn, CAJERO, "POS.ver")
    owner, cajero = _user(conn, "system_owner"), _user(conn, "cajero")
    _save(conn, owner, cajero, {"POS.ver": "DENY"})
    matrix = UserPermissionMatrixQuery(conn).matrix(cajero)
    assert "POS.ver" in matrix.role_granted and matrix.state("POS.ver") == "DENY"
    assert matrix.state("CAJA.ver") == "INHERIT"


def test_nobody_edits_their_own_permissions(conn):
    owner = _user(conn, "system_owner")
    with pytest.raises(ConfigurationPermissionDeniedError, match="propios"):
        _save(conn, owner, owner, {"POS.ver": "GRANT"})


def test_nobody_grants_what_they_do_not_have(conn):
    _grant_role(conn, GERENTE, "POS.ver")
    gerente, cajero = _user(conn, "gerente"), _user(conn, "cajero")
    _save(conn, gerente, cajero, {"POS.ver": "GRANT"})
    with pytest.raises(ConfigurationPermissionDeniedError, match="no tienes"):
        _save(conn, gerente, cajero, {"CAJA.reembolso.autorizar": "GRANT"})


def test_the_owner_is_never_denied_and_admins_take_no_exceptions(conn):
    owner, otro_owner, admin = _user(conn, "system_owner"), _user(conn, "system_owner"), _user(conn, "admin")
    with pytest.raises(ConfigurationInvalidValueError, match="dueño"):
        _save(conn, owner, otro_owner, {"POS.ver": "DENY"})
    _save(conn, owner, otro_owner, {"POS.ver": "GRANT"})  # conceder sí
    with pytest.raises(ConfigurationInvalidValueError, match="acceso total"):
        _save(conn, owner, admin, {"POS.ver": "GRANT"})


def test_without_the_permission_nothing_changes(conn):
    with pytest.raises(ConfigurationPermissionDeniedError):
        _save(conn, _user(conn, "gerente"), _user(conn, "cajero"), {"POS.ver": "GRANT"},
              authorized=False)


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_the_dialog_returns_only_changes_and_owner_cannot_be_denied(app):
    from backend.application.security.role_permission_matrix import ModulePermissions, PermissionOption
    from backend.application.security.user_permission_matrix import UserPermissionMatrix
    from frontend.desktop.modules.configuracion.dialogs.user_permissions_dialog import (
        UserPermissionsDialog,
    )

    modulos = (ModulePermissions("POS", "Punto de venta", (
        PermissionOption("POS.ver", "Ver"), PermissionOption("POS.cobrar", "Cobrar"))),)
    matriz = UserPermissionMatrix("u", "Ana", "cajero", "EDITABLE", "", frozenset({"POS.ver"}),
                                  {}, modulos)
    dlg = UserPermissionsDialog(matrix=matriz)
    combo = dlg._combos["POS.cobrar"]
    combo.setCurrentIndex(combo.findData("GRANT"))
    assert dlg.changes() == {"POS.cobrar": "GRANT"}
    dueño = UserPermissionsDialog(matrix=UserPermissionMatrix(
        "u", "Dueño", "system_owner", "GRANT_ONLY", "", frozenset(), {}, modulos))
    assert dueño._combos["POS.ver"].findData("DENY") == -1
