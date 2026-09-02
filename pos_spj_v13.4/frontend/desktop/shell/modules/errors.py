"""Canonical ModuleRegistry errors — SHELL-8 §75."""
from __future__ import annotations


class DuplicateModuleRegistrationError(ValueError):
    """A `module_id` was registered twice — caught eagerly at registration
    time, same discipline as `ServiceRegistry`'s duplicate-key guard."""


class ModuleNotFoundError(KeyError):
    """`ModuleRegistry.get()`/`require()` referenced a `module_id` nothing
    registered."""
