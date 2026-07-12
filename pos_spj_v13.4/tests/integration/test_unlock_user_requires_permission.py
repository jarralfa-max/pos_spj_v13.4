"""El desbloqueo exige CONFIG_SEGURIDAD.editar o USUARIOS.desbloquear."""
from __future__ import annotations

import pytest

from backend.application.services.user_security_service import UserSecurityService
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _locked_user(conn) -> str:
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, "
        " intentos_fallidos, bloqueado_hasta) "
        "VALUES (?, 'Beto', 'beto', 'x', 'cajero', 5, datetime('now','+15 minutes'))",
        (uid,),
    )
    return uid


def test_unlock_without_permission_fails():
    conn = make_db()
    uid = _locked_user(conn)
    svc = UserSecurityService(conn, permission_checker=lambda code: False)
    with pytest.raises(PermissionError):
        svc.unlock_user(uid, operation_id=new_uuid(), actor_id=new_uuid())
    # Sigue bloqueado
    row = conn.execute(
        "SELECT intentos_fallidos FROM usuarios WHERE id=?", (uid,)
    ).fetchone()
    assert row[0] == 5


def test_unlock_without_checker_fails_closed():
    conn = make_db()
    uid = _locked_user(conn)
    svc = UserSecurityService(conn, permission_checker=None)
    with pytest.raises(PermissionError):
        svc.unlock_user(uid, operation_id=new_uuid(), actor_id=new_uuid())


def test_unlock_accepts_usuarios_desbloquear_permission():
    conn = make_db()
    uid = _locked_user(conn)
    svc = UserSecurityService(
        conn, permission_checker=lambda code: code == "USUARIOS.desbloquear"
    )
    assert svc.unlock_user(uid, operation_id=new_uuid(), actor_id=new_uuid())["ok"]
