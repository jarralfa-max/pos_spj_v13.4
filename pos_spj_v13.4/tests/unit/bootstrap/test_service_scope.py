import pytest

from backend.bootstrap.service_container import ServiceContainer
from backend.bootstrap.service_errors import ScopeClosedError
from backend.bootstrap.service_lifetime import Lifetime
from backend.bootstrap.service_registry import ServiceRegistry


def _container(**registrations) -> ServiceContainer:
    registry = ServiceRegistry()
    for key, (factory, lifetime) in registrations.items():
        registry.register(key, factory, lifetime=lifetime)
    return ServiceContainer(registry)


def test_scope_caches_its_own_lifetime_within_the_scope():
    container = _container(a=(lambda r: object(), Lifetime.OPERATION))
    scope = container.create_scope(Lifetime.OPERATION)
    assert scope.resolve("a") is scope.resolve("a")


def test_two_separate_scopes_never_share_instances():
    container = _container(a=(lambda r: object(), Lifetime.OPERATION))
    scope1 = container.create_scope(Lifetime.OPERATION)
    scope2 = container.create_scope(Lifetime.OPERATION)
    assert scope1.resolve("a") is not scope2.resolve("a")


def test_no_shared_unit_of_work_between_operations():
    # The specific §15 rule, phrased as a scenario: a "UnitOfWork" resolved
    # from one operation scope must never be the same object a later,
    # independent operation scope resolves.
    container = _container(uow=(lambda r: {"tx": object()}, Lifetime.OPERATION))
    op1 = container.create_scope(Lifetime.OPERATION)
    op2 = container.create_scope(Lifetime.OPERATION)
    assert op1.resolve("uow") is not op2.resolve("uow")


def test_scope_delegates_singleton_lookups_to_root():
    container = _container(shared=(lambda r: object(), Lifetime.SINGLETON))
    scope = container.create_scope(Lifetime.SESSION)
    assert scope.resolve("shared") is container.resolve("shared")


def test_scope_delegates_transient_lookups_and_never_caches_them():
    container = _container(fresh=(lambda r: object(), Lifetime.TRANSIENT))
    scope = container.create_scope(Lifetime.SESSION)
    assert scope.resolve("fresh") is not scope.resolve("fresh")


def test_nested_scopes_delegate_up_the_chain():
    container = _container(
        shared=(lambda r: "singleton-value", Lifetime.SINGLETON),
        session_thing=(lambda r: object(), Lifetime.SESSION),
        op_thing=(lambda r: object(), Lifetime.OPERATION),
    )
    session_scope = container.create_scope(Lifetime.SESSION)
    op_scope = session_scope.create_scope(Lifetime.OPERATION)

    assert op_scope.resolve("shared") == "singleton-value"
    assert op_scope.resolve("session_thing") is session_scope.resolve("session_thing")
    assert op_scope.resolve("op_thing") is op_scope.resolve("op_thing")


def test_nested_scope_root_points_to_the_container():
    container = _container()
    session_scope = container.create_scope(Lifetime.SESSION)
    op_scope = session_scope.create_scope(Lifetime.OPERATION)
    assert op_scope.root is container


def test_closed_scope_raises_on_resolve():
    container = _container(a=(lambda r: object(), Lifetime.OPERATION))
    scope = container.create_scope(Lifetime.OPERATION)
    scope.close()
    assert scope.is_closed() is True
    with pytest.raises(ScopeClosedError):
        scope.resolve("a")


def test_scope_is_a_context_manager_that_closes_on_exit():
    container = _container(a=(lambda r: object(), Lifetime.OPERATION))
    with container.create_scope(Lifetime.OPERATION) as scope:
        scope.resolve("a")
        assert scope.is_closed() is False
    assert scope.is_closed() is True


def test_close_clears_the_cache():
    container = _container(a=(lambda r: object(), Lifetime.OPERATION))
    scope = container.create_scope(Lifetime.OPERATION)
    scope.resolve("a")
    scope.close()
    assert scope._cache == {}
