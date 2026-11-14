"""¿El alcance de quien otorga cubre lo que quiere otorgar? (SDLC-ARQ-PERM-002)

La guarda de escalada responde QUÉ se puede otorgar (nadie concede lo que no
tiene). Ésta responde DÓNDE: un gerente de una sucursal no da un rol en toda la
empresa ni en otra sucursal, ni edita a un usuario que no está a su alcance.

Se apoya en `AccessScopeResolver`, el mismo que decide los permisos de la sesión;
no hay una segunda lectura del alcance. Quien tiene un rol de toda la empresa
cubre todo. Falla cerrado: lo que no se puede afirmar que cubre, no lo cubre.
"""

from __future__ import annotations

from backend.application.security.access_scope import AccessScopeResolver
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)


class GrantScope:
    def __init__(self, connection) -> None:
        self._repo = SqlitePermissionRepository(connection)
        self._resolver = AccessScopeResolver(self._repo)

    def covers_company(self, actor: str) -> bool:
        return self._resolver.reach(actor).company_wide

    def covers_unit(self, actor: str, unit_id: str) -> bool:
        """Una unidad se cubre ENTERA: quien tiene una sucursal de la región no
        otorga en la región. La unidad sin sitios debajo cuenta como sí misma."""
        reach = self._resolver.reach(actor)
        if reach.company_wide:
            return True
        sitios = self._repo.site_ids_under(unit_id) or frozenset({str(unit_id)})
        return sitios <= reach.site_ids

    def covers_user(self, actor: str, user_id: str) -> bool:
        """El usuario está al alcance si opera en algún sitio que el actor cubre."""
        reach = self._resolver.reach(actor)
        if reach.company_wide:
            return True
        destino = self._resolver.reach(user_id)
        return not destino.company_wide and bool(destino.site_ids & reach.site_ids)

    def covers_all_of_user(self, actor: str, user_id: str) -> bool:
        """Para lo que vale en todos los sitios del usuario (una excepción sin
        sucursal): el actor tiene que cubrirlos todos."""
        reach = self._resolver.reach(actor)
        if reach.company_wide:
            return True
        destino = self._resolver.reach(user_id)
        return (not destino.company_wide and bool(destino.site_ids)
                and destino.site_ids <= reach.site_ids)


__all__ = ["GrantScope"]
