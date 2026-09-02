"""CompositionRoot — SHELL-5 §11.

The one place the whole dependency graph gets assembled: collect every
`ModuleProvider`'s registrations into one `ServiceRegistry`, validate the
resulting graph, then hand back a `ServiceContainer` for resolution.
Construction (`register`) and resolution (`resolve`) are deliberately two
different objects/phases — a provider never gets to resolve anything while
other providers are still registering, so wiring order can't matter.

Not a service locator: `CompositionRoot` itself is never handed to a page
or module (§11 "no debe entregarse completo a páginas o módulos") — call
sites receive whatever narrow set of resolved services they actually need,
typically via a `ServiceScope` created for one request/operation/view.
"""
from __future__ import annotations

from backend.bootstrap.dependency_graph_validator import DependencyGraphValidator
from backend.bootstrap.module_provider import ModuleProvider
from backend.bootstrap.service_container import ServiceContainer
from backend.bootstrap.service_registry import ServiceRegistry


class CompositionRoot:
    def __init__(
        self, providers: list[ModuleProvider], *, validator: DependencyGraphValidator | None = None,
    ) -> None:
        self._providers = providers
        self._validator = validator or DependencyGraphValidator()
        self._registry: ServiceRegistry | None = None
        self._container: ServiceContainer | None = None

    def build(self) -> ServiceContainer:
        """Register every provider, validate the graph, and construct the
        root container. Raises `DependencyGraphInvalidError` (with every
        issue found, not just the first) if validation fails — nothing is
        resolvable in that case, by design."""
        registry = ServiceRegistry()
        for provider in self._providers:
            provider.register(registry)
        self._validator.validate_or_raise(registry)
        self._registry = registry
        self._container = ServiceContainer(registry)
        return self._container

    @property
    def registry(self) -> ServiceRegistry:
        if self._registry is None:
            raise RuntimeError("CompositionRoot.build() no se ha ejecutado todavía.")
        return self._registry

    @property
    def container(self) -> ServiceContainer:
        if self._container is None:
            raise RuntimeError("CompositionRoot.build() no se ha ejecutado todavía.")
        return self._container
