import pytest

from frontend.desktop.shell.loading.dispatching_module_activator import (
    DispatchingModuleActivator,
    UnregisteredModuleActivatorError,
)
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor


def _module(module_id="sales_pos") -> ModuleDescriptor:
    return ModuleDescriptor(module_id=module_id, display_name=module_id)


class _RecordingActivator:
    """A minimal `ModuleActivator` (structural, not inherited) — activation
    is a method call, not a bare callable, matching every real per-module
    activator's shape."""

    def __init__(self):
        self.activated_module_ids = []

    def activate(self, module: ModuleDescriptor) -> None:
        self.activated_module_ids.append(module.module_id)


def test_is_registered_reflects_state():
    dispatcher = DispatchingModuleActivator()
    assert dispatcher.is_registered("sales_pos") is False
    dispatcher.register("sales_pos", _RecordingActivator())
    assert dispatcher.is_registered("sales_pos") is True


def test_activate_delegates_to_the_registered_activator_for_that_module_id():
    activator = _RecordingActivator()
    dispatcher = DispatchingModuleActivator()
    dispatcher.register("sales_pos", activator)
    dispatcher.activate(_module("sales_pos"))
    assert activator.activated_module_ids == ["sales_pos"]


def test_activate_routes_to_the_correct_activator_among_several():
    sales_activator, inventory_activator = _RecordingActivator(), _RecordingActivator()
    dispatcher = DispatchingModuleActivator()
    dispatcher.register("sales_pos", sales_activator)
    dispatcher.register("inventory", inventory_activator)
    dispatcher.activate(_module("inventory"))
    assert sales_activator.activated_module_ids == []
    assert inventory_activator.activated_module_ids == ["inventory"]


def test_activate_unregistered_module_id_raises():
    dispatcher = DispatchingModuleActivator()
    with pytest.raises(UnregisteredModuleActivatorError):
        dispatcher.activate(_module("does_not_exist"))


def test_activator_object_with_activate_method_works_too():
    class RealActivator:
        def __init__(self):
            self.activated = []

        def activate(self, module):
            self.activated.append(module.module_id)

    activator = RealActivator()
    dispatcher = DispatchingModuleActivator()
    dispatcher.register("sales_pos", activator)
    dispatcher.activate(_module("sales_pos"))
    assert activator.activated == ["sales_pos"]
