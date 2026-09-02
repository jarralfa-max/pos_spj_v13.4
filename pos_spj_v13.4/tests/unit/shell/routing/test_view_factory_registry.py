import pytest

from frontend.desktop.shell.routing.errors import (
    DuplicateViewFactoryRegistrationError,
    ViewFactoryNotFoundError,
)
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry


def test_register_and_get():
    registry = ViewFactoryRegistry()
    registry.register("sales.pos_view", lambda: "widget")
    assert registry.get("sales.pos_view")() == "widget"


def test_is_registered():
    registry = ViewFactoryRegistry()
    assert registry.is_registered("x") is False
    registry.register("x", lambda: object())
    assert registry.is_registered("x") is True


def test_get_returns_none_for_unknown_id():
    registry = ViewFactoryRegistry()
    assert registry.get("nope") is None


def test_require_raises_for_unknown_id():
    registry = ViewFactoryRegistry()
    with pytest.raises(ViewFactoryNotFoundError):
        registry.require("nope")


def test_duplicate_registration_raises():
    registry = ViewFactoryRegistry()
    registry.register("x", lambda: object())
    with pytest.raises(DuplicateViewFactoryRegistrationError):
        registry.register("x", lambda: object())


def test_create_view_invokes_the_factory():
    calls = []
    registry = ViewFactoryRegistry()
    registry.register("x", lambda: calls.append(1) or "created")
    result = registry.create_view("x")
    assert result == "created"
    assert calls == [1]


def test_create_view_raises_for_unknown_id():
    registry = ViewFactoryRegistry()
    with pytest.raises(ViewFactoryNotFoundError):
        registry.create_view("nope")


def test_each_call_invokes_factory_fresh():
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return object()

    registry = ViewFactoryRegistry()
    registry.register("x", factory)
    a = registry.create_view("x")
    b = registry.create_view("x")
    assert a is not b
    assert counter["n"] == 2


def test_all_ids_returns_every_registered_id():
    registry = ViewFactoryRegistry()
    registry.register("a", lambda: None)
    registry.register("b", lambda: None)
    assert set(registry.all_ids()) == {"a", "b"}
