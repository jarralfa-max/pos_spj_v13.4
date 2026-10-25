"""Un admin con permiso desbloquea a un usuario bloqueado y queda auditado."""
from __future__ import annotations

import sqlite3

import pytest

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


# `test_configuracion_ui_wires_unlock_button` y `test_list_users_dto_exposes_lock_state`
# leían `modulos/configuracion.py` y `repositories.config_repository`, ambos
# retirados. El desbloqueo vivo está en Configuración → Usuarios y Roles
# (`ConfiguracionPresenter.unlock_user`) y el estado de bloqueo en la lista lo
# prueba `tests/integration/configuracion/test_usuarios_roles_query_returns_dtos.py`.


def test_a_failed_commit_is_not_reported_as_a_successful_unlock():
    """Un `commit()` que falla no puede devolver `ok: True`.

    Tragarse el error dejaba lo peor de los dos mundos: el usuario seguía
    bloqueado —el UPDATE nunca se guardó— pero la llamada informaba éxito y
    la bitácora registraba USER_UNLOCKED. Nadie tenía cómo enterarse: ni el
    admin, que veía "Usuario desbloqueado", ni una auditoría posterior, que
    encontraría el asiento del desbloqueo sin el desbloqueo.

    El comentario que lo justificaba decía que el llamador puede ser dueño de
    la transacción. Pero `commit()` sobre una conexión sin transacción abierta
    no lanza: es una operación vacía. Lo único que este `except` llegaba a
    ocultar eran los fallos de verdad. Y el único llamador —el presentador de
    Configuración— ya traduce la excepción a "Error inesperado; revise el
    log.", así que propagarla no deja a nadie sin respuesta.
    """
    conn = make_db()
    uid = _make_locked_user(conn)

    class _ConexionConCommitRoto:
        """Todo igual salvo el commit, que falla como fallaría un disco lleno."""

        def __init__(self, real):
            self._real = real

        def __getattr__(self, nombre):
            return getattr(self._real, nombre)

        def commit(self):
            raise sqlite3.OperationalError("disk I/O error")

    servicio = UserSecurityService(
        _ConexionConCommitRoto(conn), permission_checker=lambda code: True)

    with pytest.raises(sqlite3.OperationalError):
        servicio.unlock_user(uid, operation_id=new_uuid(), actor_id=new_uuid())
