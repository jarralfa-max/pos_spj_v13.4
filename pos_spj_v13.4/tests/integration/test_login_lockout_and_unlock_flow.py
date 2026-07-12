"""Flujo completo: bloqueo por intentos fallidos → desbloqueo administrativo."""
from __future__ import annotations

import pytest

from backend.application.services.user_security_service import UserSecurityService
from backend.shared.ids import new_uuid
from core.services.auth_service import AuthService, _sha256
from tests.integration._born_clean_db import make_db


class _Repo:
    def __init__(self, db):
        self.db = db

    def get_user_by_username(self, username):
        row = self.db.execute(
            "SELECT id, nombre, usuario, password_hash, rol, sucursal_id, activo "
            "FROM usuarios WHERE usuario=?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


class _AuditStub:
    def __init__(self):
        self.events = []

    def log_change(self, **kwargs):
        self.events.append(kwargs)


class _SecurityStub:
    def clear_cache(self):
        pass

    def load_permissions(self, usuario_id, sucursal_id):
        pass


def _make_user(conn) -> str:
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, activo) "
        "VALUES (?, 'Caja Uno', 'caja1', ?, 'cajero', 1)",
        (uid, _sha256("secreta")),
    )
    return uid


def test_lockout_after_max_attempts_and_admin_unlock():
    conn = make_db()
    uid = _make_user(conn)
    auth = AuthService(_Repo(conn), security_service=_SecurityStub(), audit_service=_AuditStub())

    # 5 intentos fallidos → bloqueado
    for _ in range(AuthService.MAX_INTENTOS):
        with pytest.raises(PermissionError):
            auth.authenticate("caja1", "mala")

    row = conn.execute(
        "SELECT intentos_fallidos, bloqueado_hasta FROM usuarios WHERE id=?", (uid,)
    ).fetchone()
    assert row[0] >= AuthService.MAX_INTENTOS
    assert row[1] is not None

    # Con el usuario bloqueado, ni la contraseña correcta entra
    with pytest.raises(PermissionError):
        auth.authenticate("caja1", "secreta")

    # Desbloqueo administrativo auditado
    svc = UserSecurityService(conn, permission_checker=lambda code: True)
    svc.unlock_user(uid, operation_id=new_uuid(), actor_id=new_uuid())

    # Login exitoso tras el desbloqueo
    user = auth.authenticate("caja1", "secreta")
    assert user and str(user.get("id")) == uid
