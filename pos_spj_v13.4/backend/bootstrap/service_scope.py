"""ServiceScope — SHELL-5.

Owns exactly one `Lifetime` (SESSION, OPERATION, or VIEW) and caches
resolutions of that lifetime only; anything else delegates up the parent
chain (another scope, or eventually the root `ServiceContainer`). Scopes
nest freely — an OPERATION scope can be created from inside a SESSION
scope, etc. — but each `create_scope()` call always starts an empty cache,
which is what makes "no compartir UnitOfWork entre operaciones" (§15) true
structurally: a fresh OPERATION scope never sees a previous operation's
cached instances.
"""
from __future__ import annotations

from typing import Any

from backend.bootstrap.service_errors import ScopeClosedError
from backend.bootstrap.service_lifetime import Lifetime


class ServiceScope:
    def __init__(self, parent: Any, lifetime: Lifetime) -> None:
        self._parent = parent
        self._root = parent.root if isinstance(parent, ServiceScope) else parent
        self.lifetime = lifetime
        self._cache: dict[Any, Any] = {}
        self._closed = False

    @property
    def root(self) -> Any:
        return self._root

    def resolve(self, key: Any) -> Any:
        if self._closed:
            raise ScopeClosedError(
                f"El scope {self.lifetime.value} ya fue cerrado — no se puede resolver '{key}'."
            )
        registration = self._root._get_registration(key)
        if registration.lifetime is self.lifetime:
            if key not in self._cache:
                self._cache[key] = registration.factory(self)
            return self._cache[key]
        return self._parent.resolve(key)

    def create_scope(self, lifetime: Lifetime) -> "ServiceScope":
        return ServiceScope(self, lifetime)

    def close(self) -> None:
        self._closed = True
        self._cache.clear()

    def is_closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "ServiceScope":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False
