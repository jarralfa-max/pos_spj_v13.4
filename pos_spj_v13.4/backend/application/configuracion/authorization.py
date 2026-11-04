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

from typing import Callable, Mapping, Protocol

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
    `verificar_permiso()` call already uses.

    Auditoría de permisos 968e0bc (PER-03): antes `user_id` se aceptaba y se
    IGNORABA («la sesión ya es el usuario»). Pero los casos de uso de permisos
    usan el actor declarado en el comando para la autoedición, el escalamiento
    y la auditoría: una sesión `A` con el permiso respondía «sí» al preguntar
    por `B`, y el cambio quedaba atribuido a quien no lo hizo. Ahora concede
    sólo si el usuario consultado ES el de la sesión. No exige sucursal activa:
    Configuración es de empresa y es donde se reparan las sucursales."""

    def __init__(self, session) -> None:
        self._session = session

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        session = self._session
        if session is None or not getattr(session, "is_active", False):
            return False
        session_user_id = str(getattr(session, "user_id", "") or "").strip()
        if not session_user_id or session_user_id != str(user_id or "").strip():
            return False
        check = getattr(session, "tiene_permiso", None)
        return bool(callable(check) and check(permission_code))


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


# ── Autorización en backend de cada caso de uso (SDLC-ARQ-PERM-001) ──────────

_TEST_ACTOR = "test-actor"


class ConfiguracionActionAuthorizer:
    """Lo que recibe cada caso de uso de escritura de Configuración.

    Hasta SDLC-ARQ-PERM-001 sólo `ConfiguracionPresenter._authorize` verificaba
    el permiso: un script, otro módulo o la futura API que construyera el caso
    de uso directamente escribía credenciales de integraciones o configuración
    del sistema sin ninguna comprobación. Ahora el propio `execute` llama a
    `require()` ANTES de leer o escribir nada.

    El actor que se autoriza es el de la SESIÓN (`actor`, un proveedor), nunca
    el que trae el llamador. Si la operación declara además un actor
    (`approver_user_id`, `created_by_user_id`…) y no viene vacío, debe ser el
    mismo: así no se puede aprobar «en nombre de» otro usuario.

    Sin política (el default `unwired(ConfiguracionActionAuthorizer)` de un
    caso de uso construido sin autorizador) falla cerrado."""

    def __init__(self, policy: ConfiguracionAuthorizationPolicy | None = None,
                 actor: Callable[[], str] | None = None, *,
                 _trust_claimed_actor_for_tests: bool = False) -> None:
        self._policy = policy
        self._actor = actor
        self._trust_claimed = _trust_claimed_actor_for_tests

    @classmethod
    def for_session(cls, session) -> "ConfiguracionActionAuthorizer":
        """El autorizador de producción: verificador y actor de la sesión viva."""
        return cls(ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session)),
                   actor=lambda: str(getattr(session, "user_id", "") or ""))

    @classmethod
    def permissive_for_tests(cls) -> "ConfiguracionActionAuthorizer":
        """SÓLO pruebas aisladas (lo usa `tests/conftest.py` vía `unwired()`):
        concede cualquier permiso CONOCIDO —un código mal escrito sigue
        fallando— y toma como actor el declarado por la operación."""
        return cls(ConfiguracionAuthorizationPolicy.permissive_for_tests(),
                   _trust_claimed_actor_for_tests=True)

    def require(self, permission_code: str, *, claimed_actor: str | None = None) -> str:
        """Devuelve el actor autorizado o lanza la excepción de dominio."""
        if self._policy is None:
            raise ConfigurationAuthorizationConfigurationError(
                "Caso de uso de Configuración sin autorizador: falla cerrado. "
                "Constrúyelo con ConfiguracionActionAuthorizer.for_session(sesión)")
        claimed = str(claimed_actor or "").strip()
        actor = str(self._actor() if self._actor is not None else "").strip()
        if not actor and self._trust_claimed:
            actor = claimed or _TEST_ACTOR
        if claimed and claimed != actor:
            raise ConfigurationPermissionDeniedError(
                "El usuario declarado en la operación no es el de la sesión")
        self._policy.require(actor, permission_code)
        return actor

    def require_mapped(self, permissions_by_action: Mapping, action, *,
                       claimed_actor: str | None = None) -> str:
        """Para los casos de uso «una clase, varias acciones»: el permiso sale
        de la tabla por acción del propio módulo. Acción sin permiso → niega."""
        permission_code = _permission_for_action(permissions_by_action, action)
        if permission_code is None:
            raise ConfigurationPermissionDeniedError(
                f"Acción sin permiso definido: {getattr(action, 'value', action)}")
        return self.require(permission_code, claimed_actor=claimed_actor)


def _permission_for_action(permissions_by_action: Mapping, action) -> str | None:
    wanted = getattr(action, "value", action)
    for key, permission_code in permissions_by_action.items():
        if key is action or getattr(key, "value", key) == wanted:
            return permission_code
    return None
