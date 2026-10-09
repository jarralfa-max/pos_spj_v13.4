"""Permisos de UN usuario: lo de su rol más sus excepciones.

Cada permiso del catálogo tiene, para el usuario, uno de tres estados:
- INHERIT: lo que diga su rol (sin excepción guardada).
- GRANT: concedido aunque su rol no lo tenga.
- DENY: negado aunque su rol lo tenga.
La pantalla recibe el valor del rol y la excepción por separado para poder
mostrar ambos; el efectivo lo calcula `PermissionQueryService` al iniciar sesión.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.security.role_permission_matrix import (
    ModulePermissions,
    catalog_modules,
    role_mode,
)
from backend.infrastructure.db.repositories.security.role_permission_repository import (
    SqliteRolePermissionRepository,
)
from backend.infrastructure.db.repositories.security.user_permission_repository import (
    SqliteUserPermissionRepository,
)

INHERIT, GRANT, DENY = "INHERIT", "GRANT", "DENY"

_NOTES = {
    "FULL_ACCESS": "Su rol es administrador: tiene acceso total; no lleva excepciones.",
    "GRANT_ONLY": "Dueño de la instalación: se le pueden conceder permisos extra, nunca negar.",
    "EDITABLE": "Las excepciones rigen la próxima vez que el usuario inicie sesión.",
}


@dataclass(frozen=True)
class UserPermissionMatrix:
    user_id: str
    user_name: str
    role_name: str
    mode: str
    note: str
    role_granted: frozenset[str]
    overrides: dict
    modules: tuple[ModulePermissions, ...]

    def state(self, code: str) -> str:
        if code not in self.overrides:
            return INHERIT
        return GRANT if self.overrides[code] else DENY


class UserPermissionMatrixQuery:
    def __init__(self, connection) -> None:
        self._users = SqliteUserPermissionRepository(connection)
        self._roles = SqliteRolePermissionRepository(connection)
        self._conn = connection

    def matrix(self, user_id: str) -> UserPermissionMatrix | None:
        user = self._users.user(user_id)
        if user is None:
            return None
        user_id, name, role_name = user
        row = self._conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                                 (role_name.strip().lower(),)).fetchone()
        mode = role_mode(role_name)
        return UserPermissionMatrix(
            user_id=user_id, user_name=name, role_name=role_name, mode=mode, note=_NOTES[mode],
            role_granted=self._roles.granted(str(row[0])) if row else frozenset(),
            overrides=self._users.overrides(user_id), modules=catalog_modules())


__all__ = ["DENY", "GRANT", "INHERIT", "UserPermissionMatrix", "UserPermissionMatrixQuery"]
