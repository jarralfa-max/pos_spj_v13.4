"""BackgroundService errors — SHELL-14."""
from __future__ import annotations


class DuplicateServiceRegistrationError(ValueError):
    """A `service_id` was registered twice — caught eagerly at
    `register()`, same discipline as every other SHELL registry."""


class ServiceNotFoundError(KeyError):
    """`BackgroundServiceRegistry.require()` referenced an unregistered
    `service_id`."""


class ServiceInstanceNotBoundError(RuntimeError):
    """`BackgroundServiceSupervisor.start()` was asked to start a
    registered `service_id` that has no concrete `BackgroundService`
    instance bound via `bind()` yet — a declared-but-unwired service,
    the same "declare the shape, wire the backend later" state
    `ModuleActivator` (SHELL-13) and `view_factories` (SHELL-8) start in."""
