"""ApplicationContext/ApplicationContextService errors — SHELL-6."""
from __future__ import annotations


class BranchNotFoundError(ValueError):
    """`change_branch()` was asked to switch to a branch id that doesn't
    resolve to any active `sucursal`."""


class ContextSwitchNotAllowedError(RuntimeError):
    """The branch-switch request was rejected — either the caller lacks
    `APPLICATION_CONTEXT_SWITCH`, or there are open operations that would
    be left in an inconsistent state by switching branch mid-flight."""
