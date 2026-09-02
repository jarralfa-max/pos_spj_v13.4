import pytest

from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
from frontend.desktop.shell.background.background_service_registry import BackgroundServiceRegistry
from frontend.desktop.shell.background.errors import DuplicateServiceRegistrationError, ServiceNotFoundError


def _service(service_id, **overrides) -> BackgroundServiceDescriptor:
    kwargs = dict(display_name=service_id)
    kwargs.update(overrides)
    return BackgroundServiceDescriptor(service_id=service_id, **kwargs)


def test_register_and_get():
    registry = BackgroundServiceRegistry()
    registry.register(_service("sync"))
    assert registry.get("sync").display_name == "sync"


def test_is_registered():
    registry = BackgroundServiceRegistry()
    assert registry.is_registered("sync") is False
    registry.register(_service("sync"))
    assert registry.is_registered("sync") is True


def test_get_returns_none_for_unknown_id():
    registry = BackgroundServiceRegistry()
    assert registry.get("nope") is None


def test_require_raises_for_unknown_id():
    registry = BackgroundServiceRegistry()
    with pytest.raises(ServiceNotFoundError):
        registry.require("nope")


def test_duplicate_service_id_raises():
    registry = BackgroundServiceRegistry()
    registry.register(_service("sync"))
    with pytest.raises(DuplicateServiceRegistrationError):
        registry.register(_service("sync"))


def test_all_returns_every_registered_service():
    registry = BackgroundServiceRegistry()
    registry.register(_service("sync"))
    registry.register(_service("poller"))
    assert {s.service_id for s in registry.all()} == {"sync", "poller"}


def test_by_module_id_filters_correctly():
    registry = BackgroundServiceRegistry()
    registry.register(_service("sync", module_id="inventory"))
    registry.register(_service("poller", module_id="whatsapp"))
    assert {s.service_id for s in registry.by_module_id("inventory")} == {"sync"}
