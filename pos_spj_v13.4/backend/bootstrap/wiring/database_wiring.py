"""DatabaseModuleProvider — SHELL-16½ (new-shell live-wiring prerequisite).

Registers the live SQLite connection into the SHELL-5 `ServiceRegistry` so
`CompositionRoot`/`ServiceContainer` can hand it out like everything else —
no provider before this one has needed a live connection
(`SharedModuleProvider`/`SecurityModuleProvider` only wire cross-cutting
singletons that don't touch the database), so none registered one.

Deliberately reuses `core/db/connection.py`'s existing thread-local
connection pool (`get_connection()`) rather than opening a second,
independent connection — that pool is what every repository, migration,
and the legacy `AppContainer` already read/write through; a second
connection object to the same file would just be a second WAL writer for
no benefit and real risk (two independent SQLite connections to one file
under `check_same_thread=False` code is exactly the kind of thing that
should never be introduced casually). Registering it as SINGLETON here
does not create a second layer of caching-that-could-drift: the pool is
already a singleton-per-thread; resolving it through the container once
per thread is simply the same object handed back, cached again.

The connection's path is NOT this provider's concern — `core.db.connection.
set_db_path()` must already have been called (exactly as `main.py` already
does today, before constructing the legacy `AppContainer`) by whatever
composes this provider into a `CompositionRoot`.
"""
from __future__ import annotations

from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registry import ServiceRegistry
from core.db.connection import DatabaseWrapper, get_connection


class DatabaseModuleProvider:
    def register(self, registry: ServiceRegistry) -> None:
        registry.register(
            DatabaseWrapper,
            lambda resolver: get_connection(),
            lifetime=Lifetime.SINGLETON,
            canonical_for="DatabaseWrapper",
        )
