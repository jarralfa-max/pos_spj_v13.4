"""Canonical RouteRegistry errors — SHELL-9 §75."""
from __future__ import annotations


class DuplicateRouteRegistrationError(ValueError):
    """A `route_id` was registered twice — caught eagerly at `register()`,
    same discipline as `ServiceRegistry`/`ModuleRegistry`."""


class RouteNotFoundError(KeyError):
    """`RouteRegistry.require()`/navigation referenced a `route_id` nothing
    registered."""


class DuplicateViewFactoryRegistrationError(ValueError):
    """A `view_factory_id` was registered twice."""


class ViewFactoryNotFoundError(KeyError):
    """A route declares a `view_factory_id` nothing registered."""


class AmbiguousRouteIdError(ValueError):
    """A `route_id` doesn't carry its own identity — either a bare legacy
    code (`POS`, `CAJA`, `PRODUCCION`, `CONFIGURACION` — §45's explicit
    "no usar códigos ambiguos" list) or missing the `module.action` dotted
    form entirely, so two unrelated routes could plausibly collide on it."""


class RouteGraphInvalidError(RuntimeError):
    """`RouteRegistryValidator` found ERROR-severity issues. Carries the
    full issue list, same pattern as SHELL-5's `DependencyGraphInvalidError`."""

    def __init__(self, issues) -> None:
        self.issues = list(issues)
        summary = "; ".join(f"[{i.code}] {i.message}" for i in self.issues)
        super().__init__(f"RouteRegistry inválido: {summary}")
