import pytest

from backend.bootstrap.service_container import ServiceContainer
from backend.bootstrap.service_errors import ScopeRequiredError, ServiceNotRegisteredError
from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registry import ServiceRegistry


def _registry_with(**registrations) -> ServiceRegistry:
    registry = ServiceRegistry()
    for key, (factory, lifetime) in registrations.items():
        registry.register(key, factory, lifetime=lifetime)
    return registry


def test_singleton_resolves_to_the_same_instance():
    counter = {"n": 0}

    def factory(resolver):
        counter["n"] += 1
        return object()

    registry = _registry_with(a=(factory, Lifetime.SINGLETON))
    container = ServiceContainer(registry)

    first = container.resolve("a")
    second = container.resolve("a")
    assert first is second
    assert counter["n"] == 1


def test_application_lifetime_behaves_like_singleton():
    registry = _registry_with(a=(lambda r: object(), Lifetime.APPLICATION))
    container = ServiceContainer(registry)
    assert container.resolve("a") is container.resolve("a")


def test_transient_resolves_to_a_new_instance_every_time():
    registry = _registry_with(a=(lambda r: object(), Lifetime.TRANSIENT))
    container = ServiceContainer(registry)
    assert container.resolve("a") is not container.resolve("a")


def test_resolving_unregistered_key_raises():
    container = ServiceContainer(ServiceRegistry())
    with pytest.raises(ServiceNotRegisteredError):
        container.resolve("nope")


@pytest.mark.parametrize("lifetime", [Lifetime.SESSION, Lifetime.OPERATION, Lifetime.VIEW])
def test_resolving_scoped_lifetime_directly_raises(lifetime):
    registry = _registry_with(a=(lambda r: object(), lifetime))
    container = ServiceContainer(registry)
    with pytest.raises(ScopeRequiredError):
        container.resolve("a")


def test_factory_receives_the_container_as_resolver():
    received = {}

    def factory(resolver):
        received["resolver"] = resolver
        return object()

    registry = _registry_with(a=(factory, Lifetime.SINGLETON))
    container = ServiceContainer(registry)
    container.resolve("a")
    assert received["resolver"] is container


def test_root_property_returns_self():
    container = ServiceContainer(ServiceRegistry())
    assert container.root is container


@pytest.mark.parametrize("lifetime", [Lifetime.SINGLETON, Lifetime.APPLICATION, Lifetime.TRANSIENT])
def test_create_scope_rejects_root_lifetimes(lifetime):
    container = ServiceContainer(ServiceRegistry())
    with pytest.raises(ValueError):
        container.create_scope(lifetime)


@pytest.mark.parametrize("lifetime", [Lifetime.SESSION, Lifetime.OPERATION, Lifetime.VIEW])
def test_create_scope_accepts_scoped_lifetimes(lifetime):
    container = ServiceContainer(ServiceRegistry())
    scope = container.create_scope(lifetime)
    assert scope.lifetime is lifetime
