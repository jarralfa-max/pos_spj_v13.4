"""SharedModuleProvider — SHELL-5 §14.

Cross-cutting singletons every other provider may depend on: `AppPaths`
(where the app's data lives) and `SecretStoreGateway` (the OS credential
vault or its encrypted-local fallback — see backend/security/secrets/,
built in SHELL-1). Registered here, not per-module, so nobody re-resolves a
second `AppPaths`/secret store instance.
"""
from __future__ import annotations

from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registration import ServiceDependency
from backend.bootstrap.service_registry import ServiceRegistry
from backend.security.secrets.default_secret_store import build_default_secret_store
from backend.security.secrets.secret_store_gateway import SecretStoreGateway
from backend.shared.app_paths import AppPaths


def _build_secret_store(resolver):
    return build_default_secret_store(resolver.resolve(AppPaths))


class SharedModuleProvider:
    def register(self, registry: ServiceRegistry) -> None:
        registry.register(
            AppPaths,
            lambda resolver: AppPaths.from_environment().ensure_directories(),
            lifetime=Lifetime.SINGLETON,
            canonical_for="AppPaths",
        )
        registry.register(
            SecretStoreGateway,
            _build_secret_store,
            lifetime=Lifetime.SINGLETON,
            dependencies=[ServiceDependency(key=AppPaths)],
            canonical_for="SecretStoreGateway",
        )
