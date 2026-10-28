"""ApplicationContext — SHELL-6 §19.

An immutable snapshot of "who's using this app, from where, with what
rights, right now." Every field from §19 is present. Two fields worth
calling out because nothing like them exists yet elsewhere in the
codebase (confirmed by research before writing this):

- `workstation_id`/`workstation_type`: there is no `estaciones`/workstation
  table in the schema. `default_workstation_id()` derives a reasonable
  identity from the OS hostname rather than inventing a whole workstation
  registry this phase doesn't need.
- `locale`/`timezone`/`currency`: no canonical source for these exists
  today either (confirmed: `MonedaService` does exchange-rate conversion,
  not a session-level default currency). Sane fixed defaults
  (`es-MX`/`America/Mexico_City`/`MXN`) are used until a real
  Settings/Configuration module (a later phase) makes them configurable.

Updates happen only through `ApplicationContextService` (§20) — nothing
mutates a `ApplicationContext` in place; `SessionContext`'s "mutate in
place via set_*" pattern is exactly what this replaces.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.organization.site_capabilities import (
    blocked_permission_families,
    module_allowed,
)
from backend.domain.software_distribution.install_profile import EnabledCapabilities
from backend.security.permissions.principals import FULL_ACCESS_ROLE_NAMES

# Única lista de acceso total (auditoría de permisos 968e0bc, PER-07).
_ADMIN_ROLES = FULL_ACCESS_ROLE_NAMES

DEFAULT_LOCALE = "es-MX"
DEFAULT_TIMEZONE = "America/Mexico_City"
DEFAULT_CURRENCY = "MXN"


def default_workstation_id() -> str:
    try:
        return socket.gethostname() or "unknown-workstation"
    except OSError:
        return "unknown-workstation"


@dataclass(frozen=True)
class FeatureContext:
    """The set of feature flags enabled for the context's branch — wraps
    `FeatureFlagService.get_branch_flags()`'s result as an immutable,
    branch-scoped snapshot rather than a live, mutable cache lookup."""

    enabled_features: frozenset[str] = field(default_factory=frozenset)
    #: Flags que EXISTEN y quedaron apagados para la sucursal. Distinto de "no
    #: encendido": un flag ausente no apaga nada (p. ej. un módulo sin flag de
    #: módulo sigue visible).
    disabled_features: frozenset[str] = field(default_factory=frozenset)

    def is_enabled(self, feature_name: str) -> bool:
        return feature_name in self.enabled_features

    def is_disabled(self, feature_name: str) -> bool:
        return feature_name in self.disabled_features

    @classmethod
    def from_flags_dict(cls, flags: dict) -> "FeatureContext":
        flags = flags or {}
        return cls(
            enabled_features=frozenset(name for name, enabled in flags.items() if enabled),
            disabled_features=frozenset(name for name, enabled in flags.items() if not enabled))


@dataclass(frozen=True)
class ApplicationContext:
    installation_id: str
    company_id: str
    branch_id: str
    branch_name: str
    workstation_id: str
    workstation_type: str
    user_id: str
    user_name: str
    roles: tuple[str, ...]
    permissions: frozenset[str]
    feature_context: FeatureContext
    session_id: str
    #: Sucursales ASIGNADAS al usuario (`usuarios_sucursales`). Añadido el
    #: 2026-09-17: los contextos de ejecución de Inventario, Mermas y Cárnico
    #: leen `assigned_branch_ids` de la sesión, pero NADIE lo escribía nunca, así
    #: que el nivel "sucursales asignadas" del alcance era hueco para todos y
    #: `VIEW_ASSIGNED_BRANCHES` no podía conceder nada.
    #: Vacío NO significa "ninguna sucursal": significa "sin asignaciones
    #: explícitas", y entonces manda la sucursal propia (`branch_id`).
    assigned_branch_ids: frozenset[str] = frozenset()
    #: Capacidades HABILITADAS en esta estación por el perfil de instalación
    #: (`backend/domain/software_distribution/install_profile.py`). Distinto de
    #: los feature flags (por sucursal) y de los permisos (por usuario): un
    #: módulo no instalado se oculta, el router lo rechaza y sus familias de
    #: permisos se niegan incluso al administrador.
    capabilities: EnabledCapabilities = field(default_factory=EnabledCapabilities.everything)
    #: Capacidades del SITIO de la sesión (estructura organizacional, auditoría
    #: enterprise Fase 2): en una planta sin POS no hay punto de venta. `None` =
    #: sitio no gobernado (base sin estructura organizacional): no restringe.
    site_capabilities: frozenset[str] | None = None
    locale: str = DEFAULT_LOCALE
    timezone: str = DEFAULT_TIMEZONE
    currency: str = DEFAULT_CURRENCY
    offline_status: str = "ONLINE"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_admin(self) -> bool:
        return any(role.lower() in _ADMIN_ROLES for role in self.roles)

    def site_allows_module(self, module_id: str) -> bool:
        return module_allowed(module_id, self.site_capabilities)

    def site_blocks_permission(self, normalized_code: str) -> bool:
        """La familia del permiso es exclusiva de un módulo que este sitio no
        tiene (p. ej. `PRODUCCION.*` en una sucursal sin producción)."""
        code = str(normalized_code or "").strip().upper()
        return "." in code and code.split(".", 1)[0] in blocked_permission_families(
            self.site_capabilities)

    def with_branch(
        self, *, branch_id: str, branch_name: str, permissions: frozenset[str],
        feature_context: FeatureContext, roles: tuple[str, ...] | None = None,
        site_capabilities: frozenset[str] | None = None,
    ) -> "ApplicationContext":
        """Used only by `ApplicationContextService.change_branch()` — every
        other field carries over unchanged; permissions, feature flags, the roles
        valid at the branch and its site capabilities are branch-scoped so they're
        replaced, not merged."""
        return ApplicationContext(
            installation_id=self.installation_id, company_id=self.company_id,
            branch_id=branch_id, branch_name=branch_name,
            workstation_id=self.workstation_id, workstation_type=self.workstation_type,
            user_id=self.user_id, user_name=self.user_name,
            roles=self.roles if roles is None else tuple(roles),
            permissions=permissions, feature_context=feature_context,
            session_id=self.session_id,
            # Se propaga explícitamente: este método reconstruye el contexto
            # campo por campo, así que un campo nuevo que no se nombre aquí se
            # perdería EN SILENCIO justo al cambiar de sucursal — la operación
            # donde el alcance más importa.
            assigned_branch_ids=self.assigned_branch_ids,
            capabilities=self.capabilities,
            site_capabilities=site_capabilities,
            locale=self.locale, timezone=self.timezone,
            currency=self.currency, offline_status=self.offline_status,
            created_at=self.created_at,
        )
