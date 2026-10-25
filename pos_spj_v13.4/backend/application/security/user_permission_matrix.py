"""Permisos de UN usuario: lo de su rol, sus excepciones y el resultado.

Cada permiso del catálogo tiene, para el usuario, uno de tres estados:
- INHERIT: lo que diga su rol (sin excepción guardada).
- GRANT: concedido aunque su rol no lo tenga.
- DENY: negado aunque su rol lo tenga.

Auditoría de permisos 968e0bc (PER-08): la matriz mostraba sólo el rol y la
excepción global, así que un administrador no podía explicar por qué alguien
seguía pudiendo operar. Ahora:
- el ÁMBITO de las excepciones es «todas las sucursales» o UNA sucursal (la
  tercera capa de `PermissionQueryService`, que antes no tenía editor);
- `effective` trae, por código, el resultado y la capa que lo decidió, calculado
  por `explain_permissions` con las mismas capas que carga la sesión.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.security.permission_query_service import (
    GrantExplanation,
    PermissionQueryService,
    explain_permissions,
)
from backend.application.security.role_permission_matrix import (
    ModulePermissions,
    catalog_codes,
    catalog_modules,
    role_mode,
    role_note,
)
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.db.repositories.security.role_permission_repository import (
    SqliteRolePermissionRepository,
)
from backend.infrastructure.db.repositories.security.user_permission_repository import (
    SqliteUserPermissionRepository,
)

INHERIT, GRANT, DENY = "INHERIT", "GRANT", "DENY"

_USER_NOTES = {
    "FULL_ACCESS": "Su rol tiene acceso total (administrador o dueño); no lleva excepciones.",
    "EDITABLE": "Las excepciones rigen en sus sesiones abiertas en cuanto se guardan.",
}

#: Cómo se lee el origen de un permiso efectivo.
ORIGIN_LABELS = {
    "ACCESO_TOTAL": "acceso total",
    "SUCURSAL": "excepción en la sucursal",
    "USUARIO": "excepción del usuario",
    "ROL": "su rol",
    "NINGUNO": "nadie lo concede",
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
    #: "" = excepciones en todas las sucursales; un id = sólo en esa sucursal.
    scope_branch_id: str = ""
    branches: tuple[tuple[str, str], ...] = ()
    effective: dict = field(default_factory=dict)

    def state(self, code: str) -> str:
        if code not in self.overrides:
            return INHERIT
        return GRANT if self.overrides[code] else DENY

    def explanation(self, code: str) -> GrantExplanation | None:
        return self.effective.get(code)

    def effective_label(self, code: str) -> str:
        """«Sí — su rol», «No — excepción del usuario», …"""
        info = self.effective.get(code)
        if info is None:
            return ""
        texto = f"{'Sí' if info.effective else 'No'} — {ORIGIN_LABELS[info.origin]}"
        if info.restores_denial:
            texto += " (restituye una negación general)"
        return texto


class UserPermissionMatrixQuery:
    def __init__(self, connection) -> None:
        self._users = SqliteUserPermissionRepository(connection)
        self._roles = SqliteRolePermissionRepository(connection)
        self._resolver = PermissionQueryService(SqlitePermissionRepository(connection))
        self._conn = connection

    def matrix(self, user_id: str, branch_id: str | None = None) -> UserPermissionMatrix | None:
        user = self._users.user(user_id)
        if user is None:
            return None
        user_id, name, role_name = user
        row = self._conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                                 (role_name.strip().lower(),)).fetchone()
        mode = role_mode(role_name)
        scope = str(branch_id or "").strip()
        overrides = (self._users.branch_overrides(user_id, scope) if scope
                     else self._users.overrides(user_id))
        note = role_note(role_name) if mode == "FULL_ACCESS" else _USER_NOTES[mode]
        return UserPermissionMatrix(
            user_id=user_id, user_name=name, role_name=role_name, mode=mode, note=note,
            role_granted=self._roles.granted(str(row[0])) if row else frozenset(),
            overrides=overrides, modules=catalog_modules(), scope_branch_id=scope,
            branches=self._users.active_branches(),
            effective=explain_permissions(self._resolver, user_id, sorted(catalog_codes()),
                                          scope or None))


__all__ = ["DENY", "GRANT", "INHERIT", "ORIGIN_LABELS", "UserPermissionMatrix",
           "UserPermissionMatrixQuery"]
