import pytest

from backend.bootstrap.composition_root import CompositionRoot
from backend.bootstrap.service_errors import DependencyGraphInvalidError
from backend.bootstrap.service_lifetime import Lifetime


class FakeProvider:
    def __init__(self, register_fn):
        self._register_fn = register_fn

    def register(self, registry):
        self._register_fn(registry)


def test_build_registers_every_provider_and_returns_a_container():
    provider_a = FakeProvider(lambda r: r.register("a", lambda res: "value-a", lifetime=Lifetime.SINGLETON))
    provider_b = FakeProvider(lambda r: r.register("b", lambda res: "value-b", lifetime=Lifetime.SINGLETON))

    root = CompositionRoot([provider_a, provider_b])
    container = root.build()

    assert container.resolve("a") == "value-a"
    assert container.resolve("b") == "value-b"


def test_build_validates_the_graph_and_raises_on_invalid_wiring():
    bad_provider = FakeProvider(
        lambda r: r.register("a", lambda res: object(), lifetime=Lifetime.SINGLETON, dependencies=["missing"])
    )
    root = CompositionRoot([bad_provider])
    with pytest.raises(DependencyGraphInvalidError):
        root.build()


def test_accessing_registry_before_build_raises():
    root = CompositionRoot([])
    with pytest.raises(RuntimeError):
        _ = root.registry


def test_accessing_container_before_build_raises():
    root = CompositionRoot([])
    with pytest.raises(RuntimeError):
        _ = root.container


def test_registry_and_container_available_after_build():
    provider = FakeProvider(lambda r: r.register("a", lambda res: object(), lifetime=Lifetime.SINGLETON))
    root = CompositionRoot([provider])
    root.build()
    assert root.registry.is_registered("a")
    assert root.container.resolve("a") is not None


def test_cross_provider_dependency_resolves_correctly():
    provider_a = FakeProvider(lambda r: r.register("a", lambda res: "base", lifetime=Lifetime.SINGLETON))
    provider_b = FakeProvider(
        lambda r: r.register(
            "b", lambda res: res.resolve("a") + "-extended", lifetime=Lifetime.SINGLETON, dependencies=["a"],
        )
    )
    root = CompositionRoot([provider_a, provider_b])
    container = root.build()
    assert container.resolve("b") == "base-extended"


def test_empty_provider_list_builds_an_empty_but_valid_container():
    root = CompositionRoot([])
    container = root.build()
    assert container is not None
