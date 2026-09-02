"""Domain exceptions for the Feature Flags bounded context — SET-21.
Mirrors backend/domain/notifications/exceptions.py's shape.
"""

from __future__ import annotations


class FeatureFlagsDomainError(Exception):
    """Base for Feature Flags rule violations."""


class FeatureFlagsInvalidValueError(FeatureFlagsDomainError):
    """A field does not satisfy its validation rule."""


class FeatureFlagNotFoundError(FeatureFlagsDomainError):
    """Referenced a `FeatureFlag` id/code that does not exist."""


class FeatureFlagCodeOccupiedError(FeatureFlagsDomainError):
    """`FeatureFlag.code` must be unique; another flag already uses it."""


class FeatureFlagChangeTransitionNotAllowedError(FeatureFlagsDomainError):
    """The `FeatureFlagChangeRequest` is not in a state that allows the
    requested transition."""


class FeatureFlagApprovalRequiredError(FeatureFlagsDomainError):
    """Segregation of duties: the user who requested a flag change
    cannot also be the one who approves it (mirrors §59 of the master
    prompt, already enforced identically for configuration changes by
    `backend.domain.settings.policies.configuration_approval_policy`)."""
