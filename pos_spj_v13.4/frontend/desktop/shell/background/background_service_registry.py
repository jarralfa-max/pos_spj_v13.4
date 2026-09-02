"""BackgroundServiceRegistry — SHELL-14.

Same discipline as every other SHELL registry: duplicate `service_id`
fails eagerly at `register()`. Purely declarative — registering a
descriptor here says a service *exists*, not that it's running; binding a
real `BackgroundService` instance and starting it is
`BackgroundServiceSupervisor`'s job.
"""
from __future__ import annotations

from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
from frontend.desktop.shell.background.errors import DuplicateServiceRegistrationError, ServiceNotFoundError


class BackgroundServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, BackgroundServiceDescriptor] = {}

    def register(self, descriptor: BackgroundServiceDescriptor) -> None:
        if descriptor.service_id in self._services:
            raise DuplicateServiceRegistrationError(
                f"'{descriptor.service_id}' ya está registrado — cada servicio se registra una sola vez."
            )
        self._services[descriptor.service_id] = descriptor

    def is_registered(self, service_id: str) -> bool:
        return service_id in self._services

    def get(self, service_id: str) -> BackgroundServiceDescriptor | None:
        return self._services.get(service_id)

    def require(self, service_id: str) -> BackgroundServiceDescriptor:
        descriptor = self.get(service_id)
        if descriptor is None:
            raise ServiceNotFoundError(f"Ningún servicio registrado con id '{service_id}'.")
        return descriptor

    def all(self) -> tuple[BackgroundServiceDescriptor, ...]:
        return tuple(self._services.values())

    def by_module_id(self, module_id: str) -> tuple[BackgroundServiceDescriptor, ...]:
        return tuple(s for s in self._services.values() if s.module_id == module_id)
