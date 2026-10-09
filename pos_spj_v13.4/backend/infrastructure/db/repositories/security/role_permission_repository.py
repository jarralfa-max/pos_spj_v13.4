"""Escritura de `rol_permisos`: conceder y retirar permisos a un rol.

Separado de `SqlitePermissionRepository`, que sólo lee. No confirma: el caso de
uso abre y cierra la transacción junto con la auditoría.

Retirar BORRA la fila: en `rol_permisos` sólo cuentan las filas con
`permitido=1`, así que una fila en 0 sería ruido que parece un permiso.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.security.base import SecurityRepositoryBase
from backend.security.permissions.codes import permission_code
from backend.shared.ids import new_uuid


class SqliteRolePermissionRepository(SecurityRepositoryBase):
    def role(self, role_id: str) -> tuple[str, str] | None:
        """`(id, nombre)` del rol, o `None` si no existe."""
        row = self._query_one("SELECT id, nombre FROM roles WHERE id=?", (str(role_id),))
        return None if row is None else (str(row["id"]), str(row["nombre"] or ""))

    def granted(self, role_id: str) -> frozenset[str]:
        rows = self._query(
            "SELECT modulo, accion FROM rol_permisos WHERE rol_id=? AND permitido=1",
            (str(role_id),))
        return frozenset(permission_code(row["modulo"], row["accion"]) for row in rows)

    def grant(self, role_id: str, code: str) -> None:
        modulo, accion = code.split(".", 1)
        self._conn.execute(
            "INSERT INTO rol_permisos (id, rol_id, modulo, accion, permitido) VALUES (?,?,?,?,1)"
            " ON CONFLICT(rol_id, modulo, accion) DO UPDATE SET permitido=1",
            (new_uuid(), str(role_id), modulo, accion))

    def revoke(self, role_id: str, code: str) -> None:
        modulo, accion = code.split(".", 1)
        self._conn.execute(
            "DELETE FROM rol_permisos WHERE rol_id=? AND upper(modulo)=upper(?)"
            " AND lower(accion)=lower(?)", (str(role_id), modulo, accion))
