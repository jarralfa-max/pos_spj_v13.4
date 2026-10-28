"""353 — Varios roles por usuario, cada uno con su ámbito (auditoría enterprise,
Fase 2; decisión D4; hallazgos N01/N02/N03).

`usuarios.rol` sigue siendo el rol PRINCIPAL de la persona, con el ámbito de
siempre: su sucursal (`usuarios.sucursal_id`) más las asignadas
(`usuarios_sucursales`); un rol de acceso total, toda la empresa. Esta tabla
agrega roles ADICIONALES, cada uno con ámbito explícito:

* `COMPANY` — toda la organización (`scope_id` = id de la empresa; nunca NULL:
  un NULL no significa «todo»);
* `ORG_UNIT` — una unidad y todo lo que cuelga de ella (una región cubre sus
  sucursales, una planta sus almacenes).

Con vigencia opcional, motivo obligatorio, quién la otorgó y revocación sin
borrar (queda la historia). Sólo agrega: ningún usuario cambia de permisos.

Siembra `CONFIGURACION.usuario.asignaciones` para `system_owner` y `admin`.
Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.353")

#: Foto fija de `ConfiguracionPermissions.USUARIOS_ASIGNACIONES`.
ACCION = "usuario.asignaciones"
_ROLES = ("system_owner", "admin")

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS user_role_assignments (
        id TEXT NOT NULL PRIMARY KEY,
        user_id TEXT NOT NULL,
        role_id TEXT NOT NULL,
        scope_type TEXT NOT NULL CHECK (scope_type IN ('COMPANY', 'ORG_UNIT')),
        scope_id TEXT NOT NULL CHECK (trim(scope_id) <> ''),
        valid_from TEXT,
        valid_until TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED')),
        reason TEXT NOT NULL CHECK (trim(reason) <> ''),
        granted_by TEXT,
        created_at TEXT NOT NULL,
        revoked_at TEXT,
        revoked_by TEXT,
        revoke_reason TEXT,
        CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
        CHECK ((status = 'REVOKED') = (revoked_at IS NOT NULL))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_user_role_assignments_user"
    " ON user_role_assignments(user_id, status)",
    # Un mismo rol no se otorga dos veces con el mismo ámbito mientras esté vigente.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_role_assignments_active"
    " ON user_role_assignments(user_id, role_id, scope_type, scope_id)"
    " WHERE status = 'ACTIVE'",
)


def _sembrar(conn) -> None:
    tablas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('roles','rol_permisos')")}
    if tablas != {"roles", "rol_permisos"}:
        return
    for rol in _ROLES:
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is not None:
            conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), "CONFIGURACION", ACCION))


def create_role_assignment_schema(conn) -> None:
    for sentencia in _DDL:
        conn.execute(sentencia)


def run(conn) -> None:
    create_role_assignment_schema(conn)
    _sembrar(conn)
    conn.commit()
    logger.info("353: asignaciones de rol con ámbito listas.")


up = run
