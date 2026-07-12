"""SessionContext transporta identidad UUID string (user_id, sucursal_id)."""
from __future__ import annotations

from backend.shared.ids import new_uuid
from core.session_context import SessionContext


def test_session_user_and_branch_are_str_uuids():
    session = SessionContext()
    uid, branch = new_uuid(), new_uuid()
    session.set_user({
        "id": uid,
        "username": "ana",
        "nombre": "Ana",
        "rol": "cajero",
        "sucursal_id": branch,
        "active_branch_id": branch,
        "sucursal_nombre": "Centro",
    })
    assert session.user_id == uid
    assert isinstance(session.user_id, str)
    assert session.sucursal_id == branch
    assert isinstance(session.sucursal_id, str)
    assert session.active_branch_id == branch


def test_session_permissions_normalized_and_checked():
    session = SessionContext()
    session.set_user({"id": new_uuid(), "username": "ana", "rol": "cajero"})
    session.set_permisos({"DASHBOARD.ver", "POS.ver"})
    assert session.tiene_permiso("DASHBOARD.ver")
    assert not session.tiene_permiso("FINANZAS_UNIFICADAS.ver")


def test_session_clear_leaves_no_default_identity():
    session = SessionContext()
    session.set_user({"id": new_uuid(), "username": "ana", "rol": "cajero",
                      "sucursal_id": new_uuid()})
    session.clear()
    assert session.user_id == ""
    assert session.sucursal_id == ""
    assert session.is_active is False


def test_set_sucursal_accepts_uuid_string():
    session = SessionContext()
    branch = new_uuid()
    session.set_sucursal(branch, nombre="Norte", active_branch_id=branch)
    assert session.sucursal_id == branch
    assert session.active_branch_id == branch
