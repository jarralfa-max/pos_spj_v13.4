"""En qué sitios vale cada rol de un usuario (auditoría enterprise, Fase 2).

Un solo lugar decide el ámbito; `PermissionQueryService` (permisos de la
sesión) y `ApplicationContextBuilder` (sitio de la sesión y alcance) lo leen.

* **Rol principal** (`usuarios.rol`): vale en la sucursal propia y en las
  asignadas (`usuarios_sucursales`), como siempre. Un rol de acceso total vale
  en toda la empresa (`company_wide=True`, explícito: nunca un NULL).
* **Roles adicionales** (`user_role_assignments`, migración 353): `COMPANY`
  vale en toda la empresa; `ORG_UNIT` en la unidad y en todo lo que cuelga de
  ella (herencia por jerarquía: una región cubre sus sucursales). Sólo cuentan
  los vigentes hoy.

Un rol vale en un sitio si su ámbito lo cubre. Fuera de su ámbito no concede
nada: un cajero de Centro no es cajero en Norte por tener además un rol en Norte.

Repositorios sin estos métodos (dobles de prueba anteriores a la Fase 2) dejan
el comportamiento anterior: el rol principal sin ámbito (`supports_scopes`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from backend.domain.organization.role_assignment import effective_on
from backend.security.permissions.principals import is_full_access_role

PRIMARY = "PRIMARY"
ASSIGNMENT = "ASSIGNMENT"


@dataclass(frozen=True)
class RoleGrant:
    role_name: str
    source: str
    company_wide: bool
    site_ids: frozenset[str]
    assignment_id: str | None = None

    def covers(self, site_id: str | None) -> bool:
        if self.company_wide:
            return True
        return bool(site_id) and str(site_id) in self.site_ids


@dataclass(frozen=True)
class SiteReach:
    """Sitios que alcanza el usuario: toda la empresa o un conjunto explícito."""
    company_wide: bool
    site_ids: frozenset[str]

    def covers(self, site_id: str | None) -> bool:
        return self.company_wide or (bool(site_id) and str(site_id) in self.site_ids)


class AccessScopeResolver:
    def __init__(self, repository, *, today: Callable[[], date] = date.today) -> None:
        self._repo = repository
        self._today = today

    @property
    def supports_scopes(self) -> bool:
        return all(hasattr(self._repo, m) for m in (
            "home_branch_id", "assigned_branch_ids", "role_assignments", "site_ids_under"))

    def grants(self, user_id: str) -> tuple[RoleGrant, ...]:
        user_id = str(user_id or "").strip()
        principal = self._repo.user_role_name(user_id) if user_id else None
        if principal is None:
            return ()   # el usuario no existe: no hereda nada de nadie
        salida: list[RoleGrant] = []
        if principal:
            if is_full_access_role(principal):
                salida.append(RoleGrant(principal, PRIMARY, True, frozenset()))
            else:
                sitios = set(self._repo.assigned_branch_ids(user_id))
                propia = self._repo.home_branch_id(user_id)
                if propia:
                    sitios.add(propia)
                salida.append(RoleGrant(principal, PRIMARY, False, frozenset(sitios)))
        hoy = self._today()
        for fila in self._repo.role_assignments(user_id):
            if not effective_on(fila.get("valid_from"), fila.get("valid_until"), hoy):
                continue
            if fila["scope_type"] == "COMPANY":
                salida.append(RoleGrant(fila["role_name"], ASSIGNMENT, True, frozenset(),
                                        str(fila["id"])))
                continue
            bajo = self._repo.site_ids_under(fila["scope_id"])
            # Sin estructura organizacional (base anterior a la 351) la unidad es
            # la sucursal misma.
            sitios = bajo if bajo is not None else frozenset({str(fila["scope_id"])})
            salida.append(RoleGrant(fila["role_name"], ASSIGNMENT, False, sitios,
                                    str(fila["id"])))
        return tuple(salida)

    def roles_at(self, user_id: str, site_id: str | None) -> tuple[str, ...]:
        """Roles que valen en el sitio (sin repetir, el principal primero)."""
        vistos: list[str] = []
        for g in self.grants(user_id):
            if g.covers(site_id) and g.role_name not in vistos:
                vistos.append(g.role_name)
        return tuple(vistos)

    def company_wide_roles(self, user_id: str) -> tuple[str, ...]:
        vistos: list[str] = []
        for g in self.grants(user_id):
            if g.company_wide and g.role_name not in vistos:
                vistos.append(g.role_name)
        return tuple(vistos)

    def reach(self, user_id: str) -> SiteReach:
        concesiones = self.grants(user_id)
        if any(g.company_wide for g in concesiones):
            return SiteReach(True, frozenset())
        sitios: set[str] = set()
        for g in concesiones:
            sitios |= g.site_ids
        return SiteReach(False, frozenset(sitios))

    def covers(self, user_id: str, site_id: str | None) -> bool:
        return self.reach(user_id).covers(site_id)


__all__ = ["ASSIGNMENT", "AccessScopeResolver", "PRIMARY", "RoleGrant", "SiteReach"]
