import pytest

from backend.bootstrap.service_lifetime import (
    ROOT_LIFETIMES,
    SCOPED_LIFETIMES,
    Lifetime,
    is_lifetime_compatible,
    rank,
)


def test_singleton_and_application_share_the_same_rank():
    assert rank(Lifetime.SINGLETON) == rank(Lifetime.APPLICATION)


def test_operation_and_view_share_the_same_rank():
    assert rank(Lifetime.OPERATION) == rank(Lifetime.VIEW)


def test_rank_ordering_longest_to_shortest():
    assert rank(Lifetime.SINGLETON) < rank(Lifetime.SESSION) < rank(Lifetime.OPERATION) < rank(Lifetime.TRANSIENT)


@pytest.mark.parametrize("dependent,dependency", [
    (Lifetime.SINGLETON, Lifetime.SINGLETON),
    (Lifetime.SESSION, Lifetime.SINGLETON),
    (Lifetime.OPERATION, Lifetime.SESSION),
    (Lifetime.OPERATION, Lifetime.SINGLETON),
    (Lifetime.TRANSIENT, Lifetime.SINGLETON),
    (Lifetime.TRANSIENT, Lifetime.TRANSIENT),
])
def test_compatible_pairs(dependent, dependency):
    assert is_lifetime_compatible(dependent=dependent, dependency=dependency) is True


@pytest.mark.parametrize("dependent,dependency", [
    (Lifetime.SINGLETON, Lifetime.SESSION),
    (Lifetime.SINGLETON, Lifetime.OPERATION),
    (Lifetime.SINGLETON, Lifetime.TRANSIENT),
    (Lifetime.SESSION, Lifetime.OPERATION),
    (Lifetime.SESSION, Lifetime.TRANSIENT),
    (Lifetime.OPERATION, Lifetime.VIEW),
    (Lifetime.VIEW, Lifetime.OPERATION),
])
def test_incompatible_pairs_are_captive_dependencies(dependent, dependency):
    assert is_lifetime_compatible(dependent=dependent, dependency=dependency) is False


def test_scoped_and_root_lifetimes_partition_all_lifetimes():
    assert SCOPED_LIFETIMES | ROOT_LIFETIMES == set(Lifetime)
    assert SCOPED_LIFETIMES.isdisjoint(ROOT_LIFETIMES)
