"""ApplicationContext/ApplicationContextService errors — SHELL-6."""
from __future__ import annotations


class BranchNotFoundError(ValueError):
    """`change_branch()` was asked to switch to a branch id that doesn't
    resolve to any active `sucursal`."""


class SiteAccessDeniedError(PermissionError):
    """El usuario no tiene ningún rol cuyo ámbito cubra el sitio de esta estación
    (auditoría enterprise, Fase 2; N01). Antes la sesión tomaba la sucursal propia
    del usuario y operaba otra sucursal desde esta caja."""

    def __init__(self, site_name: str) -> None:
        super().__init__(
            f"Su usuario no tiene acceso a «{site_name}», la sucursal de esta estación. "
            "Pida a un administrador que le asigne un rol en esa sucursal.")
        self.site_name = site_name


class StationNotAnchoredError(SiteAccessDeniedError):
    """La estación no tiene sucursal anclada y el usuario no puede anclarla
    (SDLC-ARQ-TERM-002). Antes la sesión tomaba en silencio la sucursal propia
    del usuario. Hereda de `SiteAccessDeniedError` para que el inicio de sesión
    la trate igual: revoca la sesión recién abierta y muestra el motivo."""

    def __init__(self) -> None:
        PermissionError.__init__(
            self,
            "Esta estación no tiene una sucursal anclada, así que no puede operar. "
            "Un usuario con el permiso para re-anclar estaciones debe iniciar sesión y "
            "anclarla en Configuración → Empresa.")
        self.site_name = ""


class ContextSwitchNotAllowedError(RuntimeError):
    """The branch-switch request was rejected — either the caller lacks
    `APPLICATION_CONTEXT_SWITCH`, or there are open operations that would
    be left in an inconsistent state by switching branch mid-flight."""
