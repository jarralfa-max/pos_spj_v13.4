"""Domain exceptions for the Offline bounded context — SET-23.
Mirrors backend/domain/appearance/exceptions.py's shape.
"""

from __future__ import annotations


class OfflineDomainError(Exception):
    """Base for Offline rule violations."""


class OfflineInvalidValueError(OfflineDomainError):
    """A field does not satisfy its validation rule."""


class CacheEntryNotFoundError(OfflineDomainError):
    """Referenced an `OfflineCacheEntry` id that does not exist."""


class CacheExpirationPolicyNotFoundError(OfflineDomainError):
    """Referenced a `CacheExpirationPolicy` id/entity_type that does not
    exist."""


class CacheExpirationPolicyEntityTypeOccupiedError(OfflineDomainError):
    """`CacheExpirationPolicy.entity_type` must be unique; another policy
    already uses it."""
