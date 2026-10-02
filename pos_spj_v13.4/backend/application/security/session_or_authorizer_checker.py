"""Verificador para operaciones con DOS personas: quien opera (sesión) y quien
autoriza (otro usuario).

Caja exige en un reembolso que quien lo pide tenga `CAJA.reembolso.solicitar`
y que OTRA persona con `CAJA.reembolso.autorizar` lo autorice. Con sólo el
verificador de sesión, el autorizador se denegaba siempre (la sesión no es
suya); con sólo `AuthorizerPermissionChecker`, cualquiera con permisos en la
base podría operar sin sesión. Este combina ambos: el usuario de la sesión se
valida contra la sesión; cualquier otro, contra `rol_permisos`
(`AuthorizerPermissionChecker`, que ya aplica los overrides por sucursal).

El alcance por sucursal sigue la misma regla: el de la sesión con su checker de
sesión; el autorizador queda acotado por la resolución de permisos por
sucursal de `AuthorizerPermissionChecker`.
"""

from __future__ import annotations


class SessionOrAuthorizerPermissionChecker:
    def __init__(self, *, session, session_checker, authorizer_checker) -> None:
        self._session = session
        self._session_checker = session_checker
        self._authorizer_checker = authorizer_checker

    def _is_session_user(self, user_id: str) -> bool:
        return str(user_id or "").strip() == str(getattr(self._session, "user_id", "") or "").strip()

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        if self._is_session_user(user_id):
            return self._session_checker.has_permission(user_id, permission_code)
        return self._authorizer_checker.has_permission(user_id, permission_code)


class SessionOrAuthorizerBranchScopeChecker:
    def __init__(self, *, session, session_scopes) -> None:
        self._session = session
        self._session_scopes = session_scopes

    def can_access_branch(self, *, user_id: str, branch_id: str) -> bool:
        if str(user_id or "").strip() == str(getattr(self._session, "user_id", "") or "").strip():
            return self._session_scopes.can_access_branch(user_id=user_id, branch_id=branch_id)
        # El autorizador ya quedó acotado por sucursal al resolver su permiso.
        return True
