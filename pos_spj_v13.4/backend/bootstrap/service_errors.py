"""Canonical ServiceRegistry/CompositionRoot errors — SHELL-5 §75."""
from __future__ import annotations


class DuplicateServiceRegistrationError(ValueError):
    """A key was registered twice. Caught eagerly at `register()` time —
    not deferred to graph validation — so a wiring mistake fails at the
    exact `provider.register()` call that caused it."""


class ServiceNotRegisteredError(KeyError):
    """`resolve()`/a declared dependency refers to a key nothing registered."""


class ScopeRequiredError(RuntimeError):
    """A SESSION/OPERATION/VIEW-lifetime service was resolved directly from
    the root `ServiceContainer` instead of through a scope — these lifetimes
    only make sense inside `create_scope()`."""


class ScopeClosedError(RuntimeError):
    """`resolve()` was called on a `ServiceScope` after `close()`."""


class LifetimeMismatchError(RuntimeError):
    """A scope tried to resolve a key whose registered lifetime it doesn't
    own and no ancestor scope/the root container owns either — a
    programming error in how scopes were nested, not a wiring problem."""


class DependencyGraphInvalidError(RuntimeError):
    """`DependencyGraphValidator` found ERROR-severity issues. Carries the
    full issue list so the caller (bootstrap step, test) can report every
    problem at once instead of fixing them one exception at a time."""

    def __init__(self, issues) -> None:
        self.issues = list(issues)
        summary = "; ".join(f"[{i.code}] {i.message}" for i in self.issues)
        super().__init__(f"Grafo de dependencias inválido: {summary}")
