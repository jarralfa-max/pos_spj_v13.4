"""Configuración authorization — permission gate + hot authorization
(SET-1 §58/§59). Mirrors `backend.application.inventory.authorization`,
the established Compras/Inventory standard for new bounded-context
modules (dotted `MODULO.accion` codes + a `require()`-based
AuthorizationPolicy) — see `docs/refactor/settings_refactor_execution_plan.md`
"Siguiente corte recomendado: SET-1".

The presenter re-validates permission before every mutating command; the
UI never carries authorization logic. A hot authorization (an approval
signed by a second user who holds the permission and is not the
requester) always produces an `AuthorizationGrant` audit record.
"""

from __future__ import annotations

from typing import Protocol

from backend.application.configuracion.permissions import ALL_CONFIGURACION_PERMISSIONS
from backend.domain.settings.exceptions import (
    ConfigurationAuthorizationConfigurationError,
    ConfigurationPermissionDeniedError,
    ConfigurationSegregationOfDutiesError,
)
from backend.domain.settings.value_objects.authorization_grant import AuthorizationGrant


class PermissionChecker(Protocol):
    def has_permission(self, user_id: str, permission_code: str) -> bool: ...


class AllowAllConfiguracionPermissionCheckerForTests:
    """Test-only checker that grants every permission. NEVER wire in
    production — it exists so isolated tests can build a policy with an
    explicit, honest permissive checker instead of relying on a fail-open
    None."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class DenyAllConfiguracionPermissionCheckerForTests:
    """Test-only checker that denies every permission (for fail-closed
    tests)."""

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class SessionPermissionChecker:
    """Real production checker — wraps the live `core.session_context.
    SessionContext` (duck-typed, never imported: `backend/` does not
    depend on `core/`). Delegates to `session.tiene_permiso()`, which
    already resolves admin-bypass, exact-code grants, module wildcards
    (`"MODULO.*"`) and the global wildcard (`"*"`) against the real
    `rol_permisos`/`usuario_permisos`/`usuario_sucursal_permisos` grant —
    the same branch-scoped grant infrastructure every other module's
    `verificar_permiso()` call already uses. `user_id` is accepted for
    Protocol compatibility but ignored: this repo has one active session
    per process, so the session already IS the acting user (see
    `core/permissions.py::verificar_permiso`, same simplification)."""

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        if self._session is None or not getattr(self._session, "is_active", False):
            return False
        return bool(self._session.tiene_permiso(permission_code))


class ConfiguracionAuthorizationPolicy:
    def __init__(self, checker: PermissionChecker | None = None) -> None:
        self._checker = checker

    @classmethod
    def permissive_for_tests(cls) -> "ConfiguracionAuthorizationPolicy":
        """Explicit permissive policy for isolated tests / non-security
        paths. Production must be wired with a real `PermissionChecker`
        (`SessionPermissionChecker` in the live app)."""
        return cls(AllowAllConfiguracionPermissionCheckerForTests())

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        """Non-raising probe (UI gating). Fail closed: no checker → False."""
        if self._checker is None or not user_id:
            return False
        if permission_code not in ALL_CONFIGURACION_PERMISSIONS:
            return False
        return bool(self._checker.has_permission(user_id, permission_code))

    def require(self, user_id: str, permission_code: str) -> None:
        if permission_code not in ALL_CONFIGURACION_PERMISSIONS:
            raise ConfigurationPermissionDeniedError(f"Permiso desconocido: {permission_code}")
        if self._checker is None:
            # Fail closed: an unconfigured authorization gate must never
            # allow. Production wires SessionPermissionChecker; tests
            # build one explicitly (or use permissive_for_tests()).
            raise ConfigurationAuthorizationConfigurationError(
                "ConfiguracionAuthorizationPolicy requiere un PermissionChecker; "
                "usa permissive_for_tests() en pruebas aisladas"
            )
        if not user_id:
            raise ConfigurationPermissionDeniedError("Operación sin usuario autenticado")
        if not self._checker.has_permission(user_id, permission_code):
            raise ConfigurationPermissionDeniedError(
                f"El usuario {user_id} no tiene el permiso {permission_code}"
            )

    def authorize_exception(
        self,
        *,
        authorizer_user_id: str,
        requested_by: str,
        permission_code: str,
        operation_id: str,
        reason: str,
        device_id: str | None = None,
    ) -> AuthorizationGrant:
        """Validate a hot authorization and return its audit record.

        The authorizer must hold the permission and must be a distinct
        user from the requester (a hot authorization is a second pair of
        eyes, §59)."""
        if not authorizer_user_id:
            raise ConfigurationPermissionDeniedError("La autorización requiere un autorizador")
        if requested_by and authorizer_user_id == requested_by:
            raise ConfigurationSegregationOfDutiesError(
                "El autorizador de la excepción debe ser distinto del solicitante"
            )
        self.require(authorizer_user_id, permission_code)
        return AuthorizationGrant(
            permission_code=permission_code,
            requested_by=requested_by,
            authorized_by=authorizer_user_id,
            operation_id=operation_id,
            reason=reason,
            device_id=device_id,
        )
