import pytest

from backend.bootstrap.service_errors import DuplicateServiceRegistrationError
from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registration import ServiceDependency
from backend.bootstrap.service_registry import ServiceRegistry


def test_register_and_get():
    registry = ServiceRegistry()
    registry.register("a", lambda r: "instance-a", lifetime=Lifetime.SINGLETON)

    reg = registry.get("a")
    assert reg is not None
    assert reg.key == "a"
    assert reg.lifetime is Lifetime.SINGLETON


def test_is_registered():
    registry = ServiceRegistry()
    assert registry.is_registered("a") is False
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON)
    assert registry.is_registered("a") is True


def test_get_returns_none_for_unknown_key():
    registry = ServiceRegistry()
    assert registry.get("missing") is None


def test_duplicate_registration_raises():
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON)
    with pytest.raises(DuplicateServiceRegistrationError):
        registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON)


def test_register_instance_is_singleton_and_returns_exact_object():
    registry = ServiceRegistry()
    instance = object()
    registry.register_instance("a", instance)

    reg = registry.get("a")
    assert reg.lifetime is Lifetime.SINGLETON
    assert reg.factory(None) is instance


def test_dependencies_normalized_from_bare_keys():
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON, dependencies=["b", "c"])

    reg = registry.get("a")
    assert [d.key for d in reg.dependencies] == ["b", "c"]
    assert all(d.optional is False for d in reg.dependencies)


def test_dependencies_accept_explicit_service_dependency():
    registry = ServiceRegistry()
    registry.register(
        "a", lambda r: object(), lifetime=Lifetime.SINGLETON,
        dependencies=[ServiceDependency(key="b", optional=True)],
    )
    reg = registry.get("a")
    assert reg.dependencies[0].key == "b"
    assert reg.dependencies[0].optional is True


def test_canonical_for_and_deprecated_flags_are_stored():
    registry = ServiceRegistry()
    registry.register(
        "a", lambda r: object(), lifetime=Lifetime.SINGLETON,
        canonical_for="RoleX", deprecated=True,
    )
    reg = registry.get("a")
    assert reg.canonical_for == "RoleX"
    assert reg.deprecated is True


def test_registrations_returns_everything_registered():
    registry = ServiceRegistry()
    registry.register("a", lambda r: object(), lifetime=Lifetime.SINGLETON)
    registry.register("b", lambda r: object(), lifetime=Lifetime.TRANSIENT)
    keys = {reg.key for reg in registry.registrations()}
    assert keys == {"a", "b"}
