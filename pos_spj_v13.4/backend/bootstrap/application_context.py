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

_ADMIN_ROLES = frozenset({"admin", "system_owner", "superadmin", "administrador"})

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

    def is_enabled(self, feature_name: str) -> bool:
        return feature_name in self.enabled_features

    @classmethod
    def from_flags_dict(cls, flags: dict) -> "FeatureContext":
        return cls(enabled_features=frozenset(name for name, enabled in (flags or {}).items() if enabled))


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
    locale: str = DEFAULT_LOCALE
    timezone: str = DEFAULT_TIMEZONE
    currency: str = DEFAULT_CURRENCY
    offline_status: str = "ONLINE"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_admin(self) -> bool:
        return any(role.lower() in _ADMIN_ROLES for role in self.roles)

    def with_branch(
        self, *, branch_id: str, branch_name: str, permissions: frozenset[str],
        feature_context: FeatureContext,
    ) -> "ApplicationContext":
        """Used only by `ApplicationContextService.change_branch()` — every
        other field carries over unchanged; permissions and feature flags
        are branch-scoped so they're replaced, not merged."""
        return ApplicationContext(
            installation_id=self.installation_id, company_id=self.company_id,
            branch_id=branch_id, branch_name=branch_name,
            workstation_id=self.workstation_id, workstation_type=self.workstation_type,
            user_id=self.user_id, user_name=self.user_name, roles=self.roles,
            permissions=permissions, feature_context=feature_context,
            session_id=self.session_id, locale=self.locale, timezone=self.timezone,
            currency=self.currency, offline_status=self.offline_status,
            created_at=self.created_at,
        )
