# tests/test_service_registry.py — WA-4
from __future__ import annotations

import pytest

from bootstrap.service_registry import ServiceNotRegisteredError, ServiceRegistry


class TestServiceRegistry:
    def test_register_and_get(self):
        registry = ServiceRegistry()
        registry.register("thing", object())
        assert registry.has("thing") is True

    def test_get_missing_raises_service_not_registered(self):
        registry = ServiceRegistry()
        with pytest.raises(ServiceNotRegisteredError):
            registry.get("missing")

    def test_get_returns_the_same_instance(self):
        registry = ServiceRegistry()
        instance = {"a": 1}
        registry.register("thing", instance)
        assert registry.get("thing") is instance

    def test_register_none_rejected(self):
        registry = ServiceRegistry()
        with pytest.raises(ValueError):
            registry.register("thing", None)

    def test_register_empty_name_rejected(self):
        registry = ServiceRegistry()
        with pytest.raises(ValueError):
            registry.register("", object())

    def test_has_false_when_not_registered(self):
        registry = ServiceRegistry()
        assert registry.has("thing") is False

    def test_names_sorted(self):
        registry = ServiceRegistry()
        registry.register("zebra", 1)
        registry.register("apple", 2)
        assert registry.names() == ["apple", "zebra"]
