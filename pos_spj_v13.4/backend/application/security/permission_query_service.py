"""Qué permisos tiene un usuario en una sucursal.

Resuelve las tres capas que conceden permiso, de la más general a la más
específica, de modo que la más específica siempre gana:

    1. ROL          — `rol_permisos`, lo que el rol concede por defecto.
    2. USUARIO      — `usuario_permisos`, excepciones para esa persona.
    3. SUCURSAL     — `usuario_sucursal_permisos`, excepciones en esa sucursal.

En las capas 2 y 3, `permitido=0` REVOCA: no es "no dice nada", es "aquí no".
Por eso se aplican como conceder/quitar sobre el conjunto acumulado y no como
una unión — una unión haría que una revocación no tuviera ningún efecto, que es
el error clásico de este tipo de resolución.

FORMA DE LOS CÓDIGOS — el resultado sale SIEMPRE por `normalize_permission()`
(MAYÚSCULAS), porque es lo que `PermissionEvaluator` compara. Devolver aquí la
forma de almacenamiento ("POS.ver") en vez de la de comparación ("POS.VER")
haría que no coincidiera ni un solo permiso y el sistema denegara todo sin
error visible. Ver `backend/security/permissions/codes.py` y
`tests/architecture/test_permission_codes_contract.py`.

ADMINISTRADORES — un rol de acceso total (administradores y el dueño de la
instalación, `backend/security/permissions/principals.py`) devuelve `{"*"}`, el
comodín global que `PermissionEvaluator` reconoce. Antes el dueño no estaba en
esta lista aunque la sesión sí lo trataba como administrador (PER-07). Es
intencional que no se expanda al catálogo completo: si se expandiera, un permiso
nuevo añadido después del login no lo tendría el admin hasta reiniciar sesión.

ÁMBITO (auditoría enterprise, Fase 2) — un usuario puede tener varios roles,
cada uno válido en un ámbito (`access_scope.AccessScopeResolver`). Con sucursal,
sólo cuentan los roles cuyo ámbito la cubre: el principal en la sucursal propia y
las asignadas (toda la empresa si es de acceso total) y los adicionales de
`user_role_assignments` según su unidad (con herencia por jerarquía). Los
permisos son la UNIÓN de esos roles y sobre ella se aplican las excepciones,
igual que antes. Sin sucursal se conserva el comportamiento anterior: el rol
principal más los roles de toda la empresa.

PRECEDENCIA (auditoría de permisos 968e0bc, PER-06) — contrato, no accidente:
la capa más específica gana, también al CONCEDER. Una excepción de sucursal que
concede RESTITUYE un permiso negado al usuario en general: es la forma de decir
«sólo en esta sucursal». `explain()` lo marca (`restores_denial`) para que la
pantalla lo muestre en vez de que parezca una revocación sin efecto.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.security.access_scope import AccessScopeResolver
from backend.security.permissions.codes import is_granted, normalize_permission
from backend.security.permissions.principals import (
    ADMIN_ROLE_NAMES,
    is_full_access_role,
)

__all__ = [
    "ADMIN_ROLE_NAMES", "GLOBAL_WILDCARD", "GrantExplanation", "PermissionQueryService",
]

#: Comodín global que reconoce `PermissionEvaluator.has_permission()`.
GLOBAL_WILDCARD = "*"


class PermissionQueryService:
    """Consulta de sólo lectura: nunca concede ni revoca, sólo resuelve."""

    def __init__(self, repository) -> None:
        self._repository = repository

    def permission_codes_for_user(
        self, user_id: str, branch_id: str | None = None,
    ) -> frozenset[str]:
        """Códigos efectivos del usuario, ya normalizados para comparar.

        Devuelve el conjunto vacío —denegar todo— cuando el usuario no existe
        o no tiene identidad. Fallar cerrado es deliberado: un usuario que no
        se puede resolver no debe heredar los permisos de nadie.
        """
        user_id = str(user_id or "").strip()
        if not user_id:
            return frozenset()

        role_name = self._repository.user_role_name(user_id)
        if role_name is None:
            return frozenset()

        roles = self.roles_for(user_id, branch_id, primary=role_name)
        if any(is_full_access_role(r) for r in roles):
            return frozenset({GLOBAL_WILDCARD})

        codes: set[str] = set()
        for rol in roles:
            codes |= self._role_codes(rol)
        self._apply_overrides(codes, self._repository.user_overrides(user_id))
        if branch_id:
            self._apply_overrides(
                codes, self._repository.branch_overrides(user_id, str(branch_id).strip()))

        return frozenset(normalize_permission(code) for code in codes)

    def roles_for(self, user_id: str, branch_id: str | None = None, *,
                  primary: str | None = None) -> tuple[str, ...]:
        """Roles que valen para el usuario en la sucursal (ver ÁMBITO arriba)."""
        if primary is None:
            primary = self._repository.user_role_name(str(user_id or "").strip())
            if primary is None:
                return ()
        resolver = AccessScopeResolver(self._repository)
        if not resolver.supports_scopes:
            return (primary,) if primary else ()
        if branch_id and str(branch_id).strip():
            return resolver.roles_at(user_id, str(branch_id).strip())
        return tuple(dict.fromkeys(
            r for r in ((primary,) + resolver.company_wide_roles(user_id)) if r))

    def _role_codes(self, role_name: str) -> frozenset[str]:
        role_id = self._repository.role_id_for_name(role_name)
        if not role_id:
            # Un rol al que no le corresponde ninguna fila en `roles` no
            # concede nada. No es un error recuperable aquí: el usuario existe
            # pero su rol no, y conceder algo "por si acaso" sería justo lo
            # contrario de fallar cerrado.
            return frozenset()
        return self._repository.role_permission_codes(role_id)

    @staticmethod
    def _apply_overrides(codes: set[str], overrides) -> None:
        """Aplica excepciones sobre el conjunto acumulado, en su orden.

        Muta `codes` a propósito: cada capa parte del resultado de la anterior,
        que es lo que hace que la más específica gane.
        """
        for code, granted in overrides:
            if granted:
                codes.add(code)
            else:
                codes.discard(code)


@dataclass(frozen=True)
class GrantExplanation:
    """Por qué un usuario tiene (o no) un permiso en una sucursal.

    `user`/`branch` son `None` cuando esa capa no dice nada, `True` si concede
    y `False` si niega. `origin` nombra la capa que decidió: `ACCESO_TOTAL`,
    `SUCURSAL`, `USUARIO`, `ROL` o `NINGUNO`.
    """

    code: str
    role: bool
    user: bool | None
    branch: bool | None
    effective: bool
    origin: str

    @property
    def restores_denial(self) -> bool:
        """Una concesión de sucursal que deshace una negación del usuario."""
        return self.branch is True and self.user is False


def _explain_code(code: str, *, role_codes, user, branch, final) -> GrantExplanation:
    key = normalize_permission(code)
    del_rol = is_granted(role_codes, code)
    u = user.get(key)
    b = branch.get(key)
    # El resultado es el de la sesión (`final`), no uno recalculado aquí; las
    # capas sólo explican de dónde salió.
    efectivo = is_granted(final, code)
    if b is not None:
        origen = "SUCURSAL"
    elif u is not None:
        origen = "USUARIO"
    else:
        origen = "ROL" if del_rol else "NINGUNO"
    return GrantExplanation(code=code, role=del_rol, user=u, branch=b,
                            effective=efectivo, origin=origen)


def _last_wins(overrides) -> dict[str, bool]:
    """Mismo orden que `_apply_overrides`: la última fila de un código gana."""
    resultado: dict[str, bool] = {}
    for code, granted in overrides:
        resultado[normalize_permission(code)] = bool(granted)
    return resultado


def explain_permissions(service: PermissionQueryService, user_id: str, codes,
                        branch_id: str | None = None) -> dict[str, GrantExplanation]:
    """Explicación de cada código de `codes` para el usuario en la sucursal.

    Sale de las MISMAS capas y del mismo orden que `permission_codes_for_user`
    (la prueba de esta auditoría comprueba que ambos coinciden código a código):
    la pantalla no puede decir una cosa y la sesión hacer otra.
    """
    repo = service._repository
    user_id = str(user_id or "").strip()
    role_name = repo.user_role_name(user_id) if user_id else None
    if role_name is None:
        return {c: GrantExplanation(c, False, None, None, False, "NINGUNO") for c in codes}
    roles = service.roles_for(user_id, branch_id, primary=role_name)
    if any(is_full_access_role(r) for r in roles):
        return {c: GrantExplanation(c, True, None, None, True, "ACCESO_TOTAL") for c in codes}
    role_codes = frozenset(normalize_permission(c) for r in roles
                           for c in service._role_codes(r))
    user = _last_wins(repo.user_overrides(user_id))
    branch = _last_wins(repo.branch_overrides(user_id, str(branch_id).strip())) if branch_id else {}
    final = service.permission_codes_for_user(user_id, branch_id)
    return {c: _explain_code(c, role_codes=role_codes, user=user, branch=branch, final=final)
            for c in codes}
