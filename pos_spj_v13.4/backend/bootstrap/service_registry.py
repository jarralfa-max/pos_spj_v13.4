"""ServiceRegistry — SHELL-5.

The registration half of the composition root. `ModuleProvider`s only ever
see this — never `ServiceContainer`/`ServiceScope` — so a provider can
register services but can't resolve one of its own dependencies eagerly at
wiring time (which would silently bypass lifetime rules).
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from backend.bootstrap.service_errors import DuplicateServiceRegistrationError
from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registration import ServiceDependency, ServiceRegistration


class ServiceRegistry:
    def __init__(self) -> None:
        self._registrations: dict[Any, ServiceRegistration] = {}

    def register(
        self,
        key: Any,
        factory: Callable[[Any], Any],
        *,
        lifetime: Lifetime,
        dependencies: Iterable[Any | ServiceDependency] = (),
        canonical_for: str | None = None,
        deprecated: bool = False,
    ) -> None:
        if key in self._registrations:
            raise DuplicateServiceRegistrationError(
                f"'{key}' ya está registrado — cada key se registra exactamente una vez."
            )
        normalized_deps = tuple(
            dep if isinstance(dep, ServiceDependency) else ServiceDependency(key=dep)
            for dep in dependencies
        )
        self._registrations[key] = ServiceRegistration(
            key=key, lifetime=lifetime, factory=factory, dependencies=normalized_deps,
            canonical_for=canonical_for, deprecated=deprecated,
        )

    def register_instance(self, key: Any, instance: Any) -> None:
        """Convenience for a pre-built value (e.g. a config object) — always
        SINGLETON, since the instance already exists exactly once."""
        self.register(key, lambda _resolver: instance, lifetime=Lifetime.SINGLETON)

    def is_registered(self, key: Any) -> bool:
        return key in self._registrations

    def get(self, key: Any) -> ServiceRegistration | None:
        return self._registrations.get(key)

    def registrations(self) -> tuple[ServiceRegistration, ...]:
        return tuple(self._registrations.values())
