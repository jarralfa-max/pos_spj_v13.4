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
