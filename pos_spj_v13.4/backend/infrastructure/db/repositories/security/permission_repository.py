"""Lectura de las tres tablas que conceden permisos.

    rol_permisos(rol_id, modulo, accion, permitido)                -- por rol
    usuario_permisos(usuario_id, modulo, accion, permitido)        -- por usuario
    usuario_sucursal_permisos(usuario_id, sucursal_id, ...)        -- por sucursal

El repositorio sólo LEE y devuelve los códigos en FORMA DE ALMACENAMIENTO
(`permission_code`, es decir `MODULO.accion`) — que es literalmente lo que
guardan las columnas. Pasarlos a la forma de comparación (MAYÚSCULAS) es
decisión de la capa de aplicación y se hace una sola vez, en
`PermissionQueryService`. Normalizar también aquí sería duplicar la misma
decisión en dos capas: además de sobrar, haría imposible probar que la
aplicación la toma de verdad, porque los códigos ya llegarían normalizados.

Quién gana sobre quién tampoco se decide aquí — eso es una regla de negocio y
vive en `backend/application/security/permission_query_service.py`.

Las dos tablas de excepciones son opcionales: existen desde migraciones
posteriores al esquema base, así que una instalación puede no tenerlas todavía.
Se consulta `sqlite_master` antes de leerlas. Esa comprobación acepta
`type IN ('table','view')` a propósito: filtrar sólo por `'table'` haría que
una vista con ese nombre resultara invisible y el permiso se perdiera en
silencio.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.security.base import SecurityRepositoryBase
from backend.security.permissions.codes import permission_code

#: Tablas de excepción por usuario y por usuario+sucursal. `permitido=0` es una
#: REVOCACIÓN explícita, no la ausencia de un permiso: por eso se leen las
#: filas con su bandera y no sólo las concedidas.
_USER_OVERRIDES_TABLE = "usuario_permisos"
_BRANCH_OVERRIDES_TABLE = "usuario_sucursal_permisos"


class SqlitePermissionRepository(SecurityRepositoryBase):
    """Adaptador de lectura sobre las tablas de permisos."""

    def user_role_name(self, user_id: str) -> str | None:
        """Rol del usuario, o `None` si el usuario no existe.

        `usuarios.id` es UUIDv7 TEXT y es la identidad canónica: nunca se
        convierte a entero (regla de identidad §16/§17).
        """
        row = self._query_one("SELECT rol FROM usuarios WHERE id=?", (str(user_id).strip(),))
        return None if row is None else (row["rol"] or "")

    def role_id_for_name(self, role_name: str) -> str | None:
        row = self._query_one(
            "SELECT id FROM roles WHERE lower(trim(nombre))=?",
            (role_name.strip().lower(),),
        )
        return None if row is None else str(row["id"])

    def role_permission_codes(self, role_id: str) -> frozenset[str]:
        """Códigos concedidos (`permitido=1`) a un rol."""
        rows = self._query(
            "SELECT modulo, accion FROM rol_permisos WHERE rol_id=? AND permitido=1",
            (str(role_id),),
        )
        return frozenset(
            permission_code(row["modulo"], row["accion"]) for row in rows)

    def user_overrides(self, user_id: str) -> tuple[tuple[str, bool], ...]:
        """Excepciones por usuario, como `(codigo_almacenado, concedido)`."""
        if not self._table_exists(_USER_OVERRIDES_TABLE):
            return ()
        rows = self._query(
            f"""
            SELECT modulo, accion, permitido
            FROM {_USER_OVERRIDES_TABLE}
            WHERE usuario_id=?
              AND COALESCE(modulo, '') != '' AND COALESCE(accion, '') != ''
            """,
            (str(user_id).strip(),),
        )
        return tuple(
            (permission_code(row["modulo"], row["accion"]), bool(row["permitido"]))
            for row in rows
        )

    def branch_overrides(self, user_id: str, branch_id: str) -> tuple[tuple[str, bool], ...]:
        """Excepciones del usuario EN una sucursal concreta."""
        if not self._table_exists(_BRANCH_OVERRIDES_TABLE):
            return ()
        rows = self._query(
            f"""
            SELECT modulo, accion, permitido
            FROM {_BRANCH_OVERRIDES_TABLE}
            WHERE usuario_id=? AND sucursal_id=?
              AND COALESCE(modulo, '') != '' AND COALESCE(accion, '') != ''
            """,
            (str(user_id).strip(), str(branch_id).strip()),
        )
        return tuple(
            (permission_code(row["modulo"], row["accion"]), bool(row["permitido"]))
            for row in rows
        )

    # ── ámbito de los roles (auditoría enterprise, Fase 2) ─────────────────
    def home_branch_id(self, user_id: str) -> str | None:
        """Sucursal propia del usuario (`usuarios.sucursal_id`)."""
        row = self._query_one("SELECT sucursal_id FROM usuarios WHERE id=?",
                              (str(user_id).strip(),))
        valor = str((row or {}).get("sucursal_id") or "").strip()
        return valor or None

    def assigned_branch_ids(self, user_id: str) -> tuple[str, ...]:
        """Sucursales asignadas además de la propia (`usuarios_sucursales`)."""
        if not self._table_exists("usuarios_sucursales"):
            return ()
        return tuple(str(r["sucursal_id"]).strip() for r in self._query(
            "SELECT sucursal_id FROM usuarios_sucursales WHERE usuario_id=?",
            (str(user_id).strip(),)) if str(r["sucursal_id"] or "").strip())

    def role_assignments(self, user_id: str) -> tuple[dict, ...]:
        """Roles ADICIONALES vigentes por estado (la fecha la evalúa la aplicación):
        `{id, role_name, scope_type, scope_id, valid_from, valid_until}`."""
        if not self._table_exists("user_role_assignments"):
            return ()
        return tuple(self._query(
            "SELECT a.id, r.nombre AS role_name, a.scope_type, a.scope_id, a.valid_from,"
            " a.valid_until FROM user_role_assignments a JOIN roles r ON r.id = a.role_id"
            " WHERE a.user_id=? AND a.status='ACTIVE' ORDER BY a.created_at, a.id",
            (str(user_id).strip(),)))

    def site_ids_under(self, unit_id: str) -> frozenset[str] | None:
        """Sitios de operación ACTIVOS de la unidad y de todo lo que cuelga de ella
        (el id de un sitio ES su `branch_id`). `None` si la estructura
        organizacional no existe en esta base (anterior a la migración 351)."""
        if not self._table_exists("org_units"):
            return None
        filas = self._query(
            "WITH RECURSIVE down(id, depth) AS ("
            "  SELECT id, 0 FROM org_units WHERE id=?"
            "  UNION ALL SELECT u.id, down.depth + 1 FROM org_units u"
            "  JOIN down ON u.parent_id = down.id WHERE down.depth < 64)"
            " SELECT u.id FROM down JOIN org_units u ON u.id = down.id"
            " WHERE u.unit_type <> 'REGION' AND u.status = 'ACTIVE'", (str(unit_id),))
        return frozenset(str(r["id"]) for r in filas)

    def active_site_ids(self) -> frozenset[str]:
        """Todas las sucursales activas (alcance de un rol de toda la empresa)."""
        return frozenset(str(r["id"]) for r in self._query(
            "SELECT id FROM sucursales WHERE COALESCE(activa, 1) = 1"))
