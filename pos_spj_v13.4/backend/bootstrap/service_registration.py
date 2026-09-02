"""ServiceRegistration — SHELL-5.

A registration is data, not behavior: `ServiceRegistry.register()` builds
one of these per key. `dependencies` is what makes the dependency graph
inspectable *without* invoking any factory — `DependencyGraphValidator`
walks these declarations statically, it never constructs a service just to
find out what it needs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from backend.bootstrap.service_lifetime import Lifetime


@dataclass(frozen=True)
class ServiceDependency:
    key: Any
    optional: bool = False


@dataclass(frozen=True)
class ServiceRegistration:
    key: Any
    lifetime: Lifetime
    factory: Callable[[Any], Any]
    dependencies: tuple[ServiceDependency, ...] = field(default_factory=tuple)
    # Declares "this registration is THE canonical implementation of role
    # X" (§14 "dos implementaciones canónicas") — two registrations
    # claiming the same role is a graph error, independent of whether they
    # use the same lookup key.
    canonical_for: str | None = None
    # Marks a registration as a legacy/transitional shim so
    # DependencyGraphValidator can surface it as a non-fatal finding
    # (§14 "servicios legacy") without blocking the graph.
    deprecated: bool = False
