# migrations/standalone/116_roles_uuidv7_identity.py
"""
116 — Alinea la identidad de roles a UUIDv7 canónico en DBs existentes.

Bug: `role_id must be a canonical lowercase UUIDv7`. La migración 047 sembraba
roles con enteros 1..6 y `rol_permisos.rol_id` = 1..6. Con `roles.id TEXT`, esos
valores quedaban como '1'..'6' y Configuración → Permisos fallaba al validar el
UUIDv7 del rol.

Esta migración reescribe la identidad de los roles de sistema a sus UUIDv7
canónicos (backend.shared.ids.SYSTEM_ROLE_UUIDS) y propaga el cambio a las FKs
que referencian roles por id: `rol_permisos.rol_id` y `usuarios_roles.rol_id`.

Born-clean ya nace UUIDv7 desde m000; esto solo remienda bases de desarrollo
previas sin resetear.
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "Identidad UUIDv7 canónica de roles del sistema (rol_permisos/usuarios_roles)"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def run(conn: sqlite3.Connection) -> None:
    from backend.shared.ids import SYSTEM_ROLE_UUIDS

    if not _table_exists(conn, "roles"):
        return

    # Mapa nombre → id_actual (para roles de sistema conocidos).
    rows = conn.execute("SELECT id, nombre FROM roles").fetchall()
    remaps: list[tuple[str, str]] = []  # (old_id, new_uuid)
    for old_id, nombre in rows:
        canonical = SYSTEM_ROLE_UUIDS.get(str(nombre or "").strip().lower())
        if canonical and str(old_id) != canonical:
            remaps.append((str(old_id), canonical))

    for old_id, new_id in remaps:
        # Si el destino ya existe (colisión), reasignar FKs y borrar el viejo;
        # si no, actualizar el propio rol.
        exists = conn.execute("SELECT 1 FROM roles WHERE id=?", (new_id,)).fetchone()
        if exists:
            conn.execute("DELETE FROM roles WHERE id=?", (old_id,))
        else:
            conn.execute("UPDATE roles SET id=? WHERE id=?", (new_id, old_id))
        for table, col in (("rol_permisos", "rol_id"), ("usuarios_roles", "rol_id")):
            if _table_exists(conn, table):
                conn.execute(
                    f"UPDATE OR IGNORE {table} SET {col}=? WHERE {col}=?",
                    (new_id, old_id),
                )

    conn.commit()
