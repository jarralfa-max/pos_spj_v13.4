import pytest

from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.modules.startup_mode import StartupMode


class RecordingActivator:
    """A `ModuleActivator` test double that records every `activate()` call
    and raises on demand for specific module ids (via `fail_for`)."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_for: set[str] = set()

    def activate(self, module: ModuleDescriptor) -> None:
        self.calls.append(module.module_id)
        if module.module_id in self.fail_for:
            raise RuntimeError(f"{module.module_id} activation failed")


@pytest.fixture
def activator() -> RecordingActivator:
    return RecordingActivator()


@pytest.fixture
def modules() -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register(ModuleDescriptor(module_id="eager_a", display_name="A", startup_mode=StartupMode.EAGER))
    registry.register(ModuleDescriptor(module_id="eager_b", display_name="B", startup_mode=StartupMode.EAGER))
    registry.register(ModuleDescriptor(module_id="lazy_a", display_name="C", startup_mode=StartupMode.LAZY))
    registry.register(ModuleDescriptor(
        module_id="on_demand_a", display_name="D", startup_mode=StartupMode.ON_DEMAND,
    ))
    registry.register(ModuleDescriptor(
        module_id="bg_a", display_name="E", startup_mode=StartupMode.BACKGROUND_PRELOAD,
    ))
    return registry
