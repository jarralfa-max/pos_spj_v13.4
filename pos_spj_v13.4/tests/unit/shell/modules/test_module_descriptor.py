import pytest

from frontend.desktop.shell.modules.health_requirement import HealthRequirement
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode


def test_minimal_descriptor_has_sane_defaults():
    descriptor = ModuleDescriptor(module_id="transfers", display_name="Transferencias")
    assert descriptor.startup_mode is StartupMode.LAZY
    assert descriptor.routes == ()
    assert descriptor.navigation_items == ()
    assert descriptor.permissions == frozenset()
    assert descriptor.feature_flags == ()
    assert descriptor.health_requirements == ()
    assert descriptor.view_factories == {}
    assert descriptor.background_handlers == ()
    assert descriptor.required_services == ()


def test_full_descriptor_matches_master_plan_example_shape():
    descriptor = ModuleDescriptor(
        module_id="transfers",
        display_name="Transferencias",
        startup_mode=StartupMode.LAZY,
        routes=("transfers.overview", "transfers.receiving"),
        navigation_items=("nav.transfers",),
        permissions=frozenset({"TRANSFERENCIAS.ver"}),
        required_services=("inventory",),
        health_requirements=(HealthRequirement(check_name="database"),),
    )
    assert descriptor.module_id == "transfers"
    assert "transfers.receiving" in descriptor.routes
    assert descriptor.required_services == ("inventory",)


def test_rejects_empty_module_id():
    with pytest.raises(ValueError):
        ModuleDescriptor(module_id="", display_name="Transferencias")


def test_rejects_blank_module_id():
    with pytest.raises(ValueError):
        ModuleDescriptor(module_id="   ", display_name="Transferencias")


def test_rejects_empty_display_name():
    with pytest.raises(ValueError):
        ModuleDescriptor(module_id="transfers", display_name="")


def test_descriptor_is_frozen():
    descriptor = ModuleDescriptor(module_id="transfers", display_name="Transferencias")
    with pytest.raises(AttributeError):
        descriptor.module_id = "other"
