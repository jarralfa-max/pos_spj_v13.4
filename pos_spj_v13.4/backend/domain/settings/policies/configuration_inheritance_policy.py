"""ConfigurationInheritancePolicy — which scope a value may target for a
given definition, and what the fallback order looks like (§7, §9).

The actual walk over concrete candidate values (fetched from a
repository) is `services/configuration_resolution_service.py`'s job; this
policy only answers "is this scope legal here" and "in what order should
scopes be tried".
"""

from __future__ import annotations

from backend.domain.settings.enums import ScopeType
from backend.domain.settings.exceptions import ConfigurationScopeNotAllowedError

# Default specificity order used when resolving a definition's effective
# value: most specific first, GLOBAL always last (§7's worked example:
# estación → sucursal → empresa → global → default). Definitions restrict
# this to their own `allowed_scopes`; scopes absent from the caller's
# `ScopeContext` are simply skipped by the resolution service.
DEFAULT_SPECIFICITY_ORDER: tuple[ScopeType, ...] = (
    ScopeType.PRODUCT,
    ScopeType.PRODUCT_CATEGORY,
    ScopeType.CUSTOMER_SEGMENT,
    ScopeType.DELIVERY_ZONE,
    ScopeType.DEVICE,
    ScopeType.USER,
    ScopeType.ROLE,
    ScopeType.WORKSTATION,
    ScopeType.LOCATION,
    ScopeType.WAREHOUSE,
    ScopeType.CHANNEL,
    ScopeType.MODULE,
    ScopeType.PROCESS,
    ScopeType.BRANCH,
    ScopeType.COMPANY,
    ScopeType.GLOBAL,
)


def assert_scope_allowed(definition, scope_type: ScopeType) -> None:
    if not definition.allows_scope(scope_type):
        raise ConfigurationScopeNotAllowedError(
            f"{definition.key}: el ámbito {scope_type.value} no está en allowed_scopes "
            f"({sorted(s.value for s in definition.allowed_scopes)})"
        )


def resolution_order(definition) -> tuple[ScopeType, ...]:
    """Scopes to try, most specific first, restricted to what this
    definition allows (GLOBAL included only if the definition allows it)."""
    if not definition.inheritance_enabled:
        # Inheritance disabled: only the definition's own default_scope (or
        # its single allowed scope) resolves — no fallback chain.
        if definition.default_scope is not None:
            return (definition.default_scope,)
        return tuple(definition.allowed_scopes)
    return tuple(scope for scope in DEFAULT_SPECIFICITY_ORDER if scope in definition.allowed_scopes)


def canonical_override_scope(definition) -> ScopeType:
    """The one scope a non-overridable definition's value may live at:
    its own `default_scope` if set, else GLOBAL."""
    return definition.default_scope or ScopeType.GLOBAL


def assert_override_allowed(definition, scope_type: ScopeType) -> None:
    """§9's `override_allowed=False`: no scope more specific than the
    definition's canonical scope may hold its own value — every
    installation shares the one value set at `canonical_override_scope`.
    (Independent of `inheritance_enabled`, which instead controls whether
    *resolution* falls back through parent scopes at read time.)"""
    if definition.override_allowed:
        return
    canonical = canonical_override_scope(definition)
    if scope_type is not canonical:
        raise ConfigurationScopeNotAllowedError(
            f"{definition.key}: no admite overrides (override_allowed=False) — "
            f"solo puede definirse en el ámbito {canonical.value}, no en {scope_type.value}."
        )
