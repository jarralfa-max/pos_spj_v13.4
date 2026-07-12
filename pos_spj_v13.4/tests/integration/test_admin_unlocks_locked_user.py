"""Un admin con permiso desbloquea a un usuario bloqueado y queda auditado."""
from __future__ import annotations

from backend.application.services.user_security_service import UserSecurityService
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _make_locked_user(conn) -> str:
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, "
        " intentos_fallidos, bloqueado_hasta, locked_reason) "
        "VALUES (?, 'Ana', 'ana', 'x', 'cajero', 5, datetime('now','+15 minutes'), "
        " 'intentos fallidos')",
        (uid,),
    )
    return uid


def test_admin_unlocks_locked_user():
    conn = make_db()
    uid = _make_locked_user(conn)
    actor = new_uuid()

    svc = UserSecurityService(conn, permission_checker=lambda code: True)
    estado = svc.get_lock_status(uid)
    assert estado["bloqueado"] is True
    assert estado["intentos_fallidos"] == 5

    result = svc.unlock_user(uid, operation_id=new_uuid(), actor_id=actor)
    assert result["ok"] is True

    row = conn.execute(
        "SELECT intentos_fallidos, bloqueado_hasta, locked_reason "
        "FROM usuarios WHERE id=?", (uid,),
    ).fetchone()
    assert row[0] == 0 and row[1] is None and row[2] is None

    audit = conn.execute(
        "SELECT accion, modulo, entidad_id, usuario, detalles FROM audit_logs "
        "WHERE accion='USER_UNLOCKED'"
    ).fetchone()
    assert audit is not None
    assert audit[1] == "CONFIG_SEGURIDAD"
    assert audit[2] == uid
    assert audit[3] == actor
    assert "operation_id" in (audit[4] or "")
