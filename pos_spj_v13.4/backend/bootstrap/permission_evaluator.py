"""PermissionEvaluator — SHELL-6 §15 (listed as a SESSION-lifetime example).

Pure evaluation over an already-built `ApplicationContext.permissions` set —
it never queries the database itself. Loading permission codes from
`rol_permisos` stays `PermissionQueryService.permission_codes_for_user()`'s
job (existing, canonical); this class only answers "does the context I was
built from allow X," the same wildcard rules `SessionContext.tiene_permiso()`
used (admin bypass, exact code, `MODULE.*`, global `*`) — reusing
`normalize_permission()` rather than re-implementing normalization.
"""
from __future__ import annotations

from backend.security.permissions.codes import normalize_permission

from backend.bootstrap.application_context import ApplicationContext


class PermissionEvaluator:
    def __init__(self, context: ApplicationContext) -> None:
        self._context = context

    def has_permission(self, code: str) -> bool:
        normalized = normalize_permission(code)
        # Un módulo NO instalado en esta estación (perfil de instalación) no se
        # concede a nadie, administrador incluido: es la mitad backend de
        # "oculto y bloqueado"; la otra mitad es el menú y el router.
        if self._context.capabilities.permission_blocked(normalized):
            return False
        if self._context.is_admin():
            return True
        permissions = self._context.permissions
        if "*" in permissions or normalized in permissions:
            return True
        module = normalized.split(".", 1)[0] if "." in normalized else ""
        return bool(module) and f"{module}.*" in permissions

    def require_permission(self, code: str, *, action: str = "") -> None:
        if not self.has_permission(code):
            raise PermissionError(f"No tiene permiso para: {action or code}")
