"""ServiceContainer — SHELL-5.

The root resolver, built from an already-validated `ServiceRegistry`
(`CompositionRoot.build()` validates before constructing one — this class
does not validate, it only resolves). Resolves SINGLETON/APPLICATION
eagerly-cached and TRANSIENT freshly every call; SESSION/OPERATION/VIEW
lifetimes are only reachable through `create_scope()` — resolving one
directly raises `ScopeRequiredError` rather than silently picking a
lifetime for you.
"""
from __future__ import annotations

from typing import Any

from backend.bootstrap.service_errors import ScopeRequiredError, ServiceNotRegisteredError
from backend.bootstrap.service_lifetime import SCOPED_LIFETIMES, Lifetime
from backend.bootstrap.service_registry import ServiceRegistry
from backend.bootstrap.service_scope import ServiceScope


class ServiceContainer:
    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry
        self._singletons: dict[Any, Any] = {}

    @property
    def root(self) -> "ServiceContainer":
        return self

    def resolve(self, key: Any) -> Any:
        registration = self._get_registration(key)
        if registration.lifetime in (Lifetime.SINGLETON, Lifetime.APPLICATION):
            if key not in self._singletons:
                self._singletons[key] = registration.factory(self)
            return self._singletons[key]
        if registration.lifetime is Lifetime.TRANSIENT:
            return registration.factory(self)
        raise ScopeRequiredError(
            f"'{key}' tiene lifetime {registration.lifetime.value} — debe resolverse "
            f"a través de create_scope({registration.lifetime.value}), no directamente "
            f"del contenedor raíz."
        )

    def create_scope(self, lifetime: Lifetime) -> ServiceScope:
        if lifetime not in SCOPED_LIFETIMES:
            raise ValueError(
                f"create_scope() es solo para lifetimes con scope explícito "
                f"({', '.join(l.value for l in SCOPED_LIFETIMES)}); recibido {lifetime.value}."
            )
        return ServiceScope(self, lifetime)

    def _get_registration(self, key: Any):
        registration = self._registry.get(key)
        if registration is None:
            raise ServiceNotRegisteredError(f"Nada registrado bajo la key '{key}'.")
        return registration
