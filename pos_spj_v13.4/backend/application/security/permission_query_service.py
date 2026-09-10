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

ADMINISTRADORES — un rol administrador devuelve `{"*"}`, el comodín global que
`PermissionEvaluator` reconoce. Es intencional que no se expanda al catálogo
completo: si se expandiera, un permiso nuevo añadido después del login no lo
tendría el admin hasta reiniciar sesión.
"""

from __future__ import annotations

from backend.security.permissions.codes import normalize_permission

#: Nombres de rol con acceso total. Se comparan en minúsculas y sin espacios.
#: Coincide con `ApplicationContext.is_admin()`, que decide lo mismo desde el
#: otro lado (el contexto ya construido).
ADMIN_ROLE_NAMES = frozenset({"admin", "superadmin", "administrador"})

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

        if role_name.strip().lower() in ADMIN_ROLE_NAMES:
            return frozenset({GLOBAL_WILDCARD})

        codes = set(self._role_codes(role_name))
        self._apply_overrides(codes, self._repository.user_overrides(user_id))
        if branch_id:
            self._apply_overrides(
                codes, self._repository.branch_overrides(user_id, str(branch_id).strip()))

        return frozenset(normalize_permission(code) for code in codes)

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
