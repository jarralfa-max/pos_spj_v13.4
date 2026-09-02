"""Domain exceptions for the Settings (Configuration Governance) bounded
context — SET-2. Mirrors backend/domain/crm/exceptions.py's shape.
"""

from __future__ import annotations


class ConfigurationDomainError(Exception):
    """Base for Settings/Configuration Governance rule violations."""


class ConfigurationDefinitionNotFoundError(ConfigurationDomainError):
    """Referenced a `ConfigurationDefinition` key that does not exist."""


class ConfigurationValueNotFoundError(ConfigurationDomainError):
    """Referenced a `ConfigurationValue` id that does not exist."""


class ConfigurationInvalidValueError(ConfigurationDomainError):
    """A raw value does not satisfy its definition's `value_type`, allowed
    values, or validation constraints."""


class ConfigurationScopeNotAllowedError(ConfigurationDomainError):
    """The scope requested for a value is not in the definition's
    `allowed_scopes`, or the scope's identity requirement (UUIDv7 vs. code)
    was violated."""


class ConfigurationApprovalRequiredError(ConfigurationDomainError):
    """The definition requires approval and the value has not been
    approved — it cannot be activated directly from DRAFT."""


class ConfigurationActivationNotAllowedError(ConfigurationDomainError):
    """The value is not in a state that can transition to ACTIVE/SCHEDULED
    (e.g. still DRAFT, already ACTIVE, or terminal)."""


class ConfigurationRollbackNotAllowedError(ConfigurationDomainError):
    """The value is not in a state that can be rolled back (only ACTIVE or
    EXPIRED versions may be rolled back)."""


class SensitiveConfigurationAccessDeniedError(ConfigurationDomainError):
    """An attempt to read/write a `sensitive` definition's raw value
    without the elevated capability the sensitive-configuration policy
    requires."""


class WorkstationNotFoundError(ConfigurationDomainError):
    """Referenced a `Workstation` id/code that does not exist."""


class BranchProfileNotFoundError(ConfigurationDomainError):
    """Referenced a `BranchProfile` (governance record) branch_id that
    does not exist."""


class WorkstationTransitionNotAllowedError(ConfigurationDomainError):
    """The workstation is not in a state that allows the requested
    transition (e.g. checking in from BLOCKED/RETIRED, or reactivating a
    RETIRED workstation — retirement is terminal)."""


# ── SET-1 — Seguridad (permisos/alcances/segregación/autorización) ─────────

class ConfigurationPermissionDeniedError(ConfigurationDomainError):
    """The acting user does not hold the permission code a Configuración
    command requires, or the command ran with no authenticated user."""


class ConfigurationAuthorizationConfigurationError(ConfigurationDomainError):
    """`ConfiguracionAuthorizationPolicy` was invoked without a
    `PermissionChecker` wired — a configuration error, not a user-facing
    denial (fail closed: an unconfigured gate must never allow)."""


class ConfigurationSegregationOfDutiesError(ConfigurationDomainError):
    """A hot-authorization exception was requested with the same user as
    both requester and authorizer — a second, distinct pair of eyes is
    required (§59)."""
