"""Escritura de `usuario_permisos`: excepciones de permiso de UN usuario.

`permitido=1` concede algo que su rol no tiene; `permitido=0` niega algo que su
rol sí tiene (lo aplica `PermissionQueryService._apply_overrides`). Sin fila,
el usuario tiene exactamente lo de su rol.

La tabla no tiene llave única por (usuario, módulo, acción), así que fijar una
excepción BORRA antes las que hubiera para ese código: dos filas del mismo
permiso se aplicarían en orden y la última ganaría sin que nadie lo vea.
No confirma: el caso de uso cierra la transacción junto con la auditoría.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.security.base import SecurityRepositoryBase
from backend.security.permissions.codes import permission_code
from backend.shared.ids import new_uuid


class SqliteUserPermissionRepository(SecurityRepositoryBase):
    def user(self, user_id: str) -> tuple[str, str, str] | None:
        """`(id, nombre visible, rol)` o `None`."""
        row = self._query_one(
            "SELECT id, COALESCE(NULLIF(nombre,''), usuario) AS nombre, COALESCE(rol,'') AS rol"
            " FROM usuarios WHERE id=?", (str(user_id),))
        return None if row is None else (str(row["id"]), str(row["nombre"]), str(row["rol"]))

    def overrides(self, user_id: str) -> dict[str, bool]:
        rows = self._query(
            "SELECT modulo, accion, permitido FROM usuario_permisos WHERE usuario_id=?",
            (str(user_id),))
        return {permission_code(r["modulo"], r["accion"]): bool(r["permitido"]) for r in rows}

    def clear(self, user_id: str, code: str) -> None:
        modulo, accion = code.split(".", 1)
        self._conn.execute(
            "DELETE FROM usuario_permisos WHERE usuario_id=? AND upper(modulo)=upper(?)"
            " AND lower(accion)=lower(?)", (str(user_id), modulo, accion))

    def set(self, user_id: str, code: str, granted: bool) -> None:
        self.clear(user_id, code)
        modulo, accion = code.split(".", 1)
        self._conn.execute(
            "INSERT INTO usuario_permisos (id, usuario_id, modulo, accion, permitido)"
            " VALUES (?,?,?,?,?)", (new_uuid(), str(user_id), modulo, accion, 1 if granted else 0))
