"""RBAC con usuarios UUID: sin int(UUID), overrides y restricciones por sucursal."""
from __future__ import annotations

from backend.shared.ids import new_uuid
from repositories.config_repository import ConfigRepository
from tests.integration._born_clean_db import make_db


def _role(conn, nombre: str) -> str:
    rid = new_uuid()
    conn.execute("INSERT INTO roles (id, nombre) VALUES (?, ?)", (rid, nombre))
    return rid


def _grant_role(conn, rol_id: str, modulo: str, accion: str):
    conn.execute(
        "INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
        "VALUES (?, ?, ?, ?, 1)",
        (new_uuid(), rol_id, modulo, accion),
    )


def _user(conn, rol: str) -> str:
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol) "
        "VALUES (?, 'U', ?, 'x', ?)",
        (uid, f"u_{uid[:8]}", rol),
    )
    return uid


def test_permissions_resolve_for_uuid_user_without_int_cast():
    conn = make_db()
    rid = _role(conn, "cajero_test")
    _grant_role(conn, rid, "POS", "ver")
    _grant_role(conn, rid, "DASHBOARD", "ver")
    uid = _user(conn, "cajero_test")

    repo = ConfigRepository(conn)
    # Antes: int(row[0]) → ValueError con UUID. Ahora resuelve sin castear.
    permisos = repo.permission_codes_for_user(uid)
    from core.security.permission_catalog import normalize_permission
    assert normalize_permission("POS.ver") in permisos
    assert normalize_permission("DASHBOARD.ver") in permisos


def test_user_permission_overrides_use_uuid():
    conn = make_db()
    rid = _role(conn, "rol_override")
    _grant_role(conn, rid, "POS", "ver")
    uid = _user(conn, "rol_override")

    # Override positivo y negativo referenciando usuario_id UUID
    conn.execute(
        "INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido) "
        "VALUES (?, ?, 'CLIENTES', 'ver', 1)",
        (new_uuid(), uid),
    )
    conn.execute(
        "INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido) "
        "VALUES (?, ?, 'POS', 'ver', 0)",
        (new_uuid(), uid),
    )
    from core.security.permission_catalog import normalize_permission
    permisos = ConfigRepository(conn).permission_codes_for_user(uid)
    assert normalize_permission("CLIENTES.ver") in permisos
    assert normalize_permission("POS.ver") not in permisos


def test_admin_user_gets_wildcard():
    conn = make_db()
    uid = _user(conn, "admin")
    assert ConfigRepository(conn).permission_codes_for_user(uid) == {"*"}


def test_unknown_user_returns_empty_set():
    conn = make_db()
    assert ConfigRepository(conn).permission_codes_for_user(new_uuid()) == set()
