"""Bug 9: role_id must be a canonical lowercase UUIDv7.

Causa: 047 sembraba roles con enteros 1..6 y rbac.py sin id. Corregido en el
origen (m000 born-clean UUIDv7, rbac con UUID canónico, 116 remienda DBs viejas).
"""
from __future__ import annotations

import importlib
import sqlite3
from uuid import UUID

from backend.shared.ids import SYSTEM_ROLE_UUIDS
from repositories.config_repository import ConfigRepository
from tests.integration._born_clean_db import make_db

MIG116 = importlib.import_module("migrations.standalone.116_roles_uuidv7_identity")


def _is_canonical_v7(value: str) -> bool:
    parsed = UUID(str(value))
    return parsed.version == 7 and str(value) == str(parsed).lower()


def test_born_clean_roles_have_canonical_uuidv7():
    conn = make_db()
    rows = conn.execute("SELECT id, nombre FROM roles").fetchall()
    assert rows, "m000 debe sembrar roles del sistema"
    for rid, nombre in rows:
        assert _is_canonical_v7(rid), f"rol {nombre} tiene id no-UUIDv7: {rid}"
        assert str(rid) == SYSTEM_ROLE_UUIDS.get(str(nombre).lower(), str(rid))


def test_save_role_permissions_does_not_raise_uuid_error():
    conn = make_db()
    repo = ConfigRepository(conn)
    cajero_id = conn.execute("SELECT id FROM roles WHERE nombre='cajero'").fetchone()[0]
    # No debe lanzar "role_id must be a canonical lowercase UUIDv7"
    repo.save_role_permissions(cajero_id, {("POS", "ver"): True, ("CAJA", "crear"): True})
    saved = repo.role_permissions(cajero_id)
    assert saved.get(("POS", "ver")) is True


def test_cajero_has_dashboard_ver():
    conn = make_db()
    cajero_id = conn.execute("SELECT id FROM roles WHERE nombre='cajero'").fetchone()[0]
    perms = ConfigRepository(conn).role_permissions(cajero_id)
    assert perms.get(("DASHBOARD", "ver")) is True


def test_migration_116_remaps_integer_role_ids():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT UNIQUE, descripcion TEXT, activo INTEGER DEFAULT 1);
        CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT, accion TEXT, permitido INTEGER,
                                   UNIQUE(rol_id, modulo, accion));
        CREATE TABLE usuarios_roles (usuario_id TEXT, rol_id TEXT, sucursal_id TEXT,
                                     PRIMARY KEY(usuario_id, rol_id, sucursal_id));
        INSERT INTO roles VALUES ('3','cajero','Solo ventas',1);
        INSERT INTO rol_permisos VALUES ('p1','3','POS','ver',1);
        INSERT INTO usuarios_roles VALUES ('u1','3','b1');
    """)
    MIG116.run(conn)
    canonical = SYSTEM_ROLE_UUIDS["cajero"]
    assert conn.execute("SELECT id FROM roles WHERE nombre='cajero'").fetchone()[0] == canonical
    assert conn.execute("SELECT rol_id FROM rol_permisos WHERE modulo='POS'").fetchone()[0] == canonical
    assert conn.execute("SELECT rol_id FROM usuarios_roles WHERE usuario_id='u1'").fetchone()[0] == canonical
    # Idempotente
    MIG116.run(conn)
    assert conn.execute("SELECT id FROM roles WHERE nombre='cajero'").fetchone()[0] == canonical


def test_rbac_seed_uses_canonical_role_uuids():
    from security.rbac import inicializar_rbac

    conn = make_db()
    inicializar_rbac(conn)  # idempotente sobre roles ya sembrados
    for rid, nombre in conn.execute("SELECT id, nombre FROM roles").fetchall():
        assert _is_canonical_v7(rid), f"rbac dejó rol {nombre} con id no-UUIDv7: {rid}"


def test_047_no_longer_seeds_integer_roles():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2]
           / "migrations" / "standalone" / "047_v13_schema.py").read_text(encoding="utf-8")
    assert "VALUES(1,'admin'" not in src
    assert "rol_permisos(rol_id,modulo,accion,permitido) VALUES(1," not in src
