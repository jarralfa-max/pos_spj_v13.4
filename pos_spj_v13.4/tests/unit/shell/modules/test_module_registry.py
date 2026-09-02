from datetime import datetime, timezone

import pytest

from backend.bootstrap.health.health_status import HealthCheckResult, HealthReport, HealthStatus
from frontend.desktop.shell.modules.errors import DuplicateModuleRegistrationError, ModuleNotFoundError
from frontend.desktop.shell.modules.health_requirement import HealthRequirement
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry
from frontend.desktop.shell.modules.startup_mode import StartupMode

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _descriptor(module_id, **overrides) -> ModuleDescriptor:
    kwargs = dict(module_id=module_id, display_name=module_id.title())
    kwargs.update(overrides)
    return ModuleDescriptor(**kwargs)


class FakeProvider:
    def __init__(self, descriptor):
        self._descriptor = descriptor

    def describe(self):
        return self._descriptor


def test_register_and_get():
    registry = ModuleRegistry()
    registry.register(_descriptor("transfers"))
    assert registry.get("transfers").display_name == "Transfers"


def test_is_registered():
    registry = ModuleRegistry()
    assert registry.is_registered("transfers") is False
    registry.register(_descriptor("transfers"))
    assert registry.is_registered("transfers") is True


def test_get_returns_none_for_unknown_module():
    registry = ModuleRegistry()
    assert registry.get("nope") is None


def test_require_raises_for_unknown_module():
    registry = ModuleRegistry()
    with pytest.raises(ModuleNotFoundError):
        registry.require("nope")


def test_require_returns_descriptor_when_present():
    registry = ModuleRegistry()
    registry.register(_descriptor("pos"))
    assert registry.require("pos").module_id == "pos"


def test_duplicate_module_id_raises():
    registry = ModuleRegistry()
    registry.register(_descriptor("transfers"))
    with pytest.raises(DuplicateModuleRegistrationError):
        registry.register(_descriptor("transfers"))


def test_register_from_provider():
    registry = ModuleRegistry()
    registry.register_from_provider(FakeProvider(_descriptor("inventory")))
    assert registry.is_registered("inventory") is True


def test_all_returns_every_registered_module():
    registry = ModuleRegistry()
    registry.register(_descriptor("pos"))
    registry.register(_descriptor("inventory"))
    assert {m.module_id for m in registry.all()} == {"pos", "inventory"}


def test_by_startup_mode_filters_correctly():
    registry = ModuleRegistry()
    registry.register(_descriptor("pos", startup_mode=StartupMode.EAGER))
    registry.register(_descriptor("finance", startup_mode=StartupMode.LAZY))
    registry.register(_descriptor("hr", startup_mode=StartupMode.LAZY))

    eager = registry.by_startup_mode(StartupMode.EAGER)
    lazy = registry.by_startup_mode(StartupMode.LAZY)
    assert {m.module_id for m in eager} == {"pos"}
    assert {m.module_id for m in lazy} == {"finance", "hr"}


def test_owner_of_route_returns_the_declaring_module():
    registry = ModuleRegistry()
    registry.register(_descriptor("transfers", routes=("transfers.overview",)))
    assert registry.owner_of_route("transfers.overview") == "transfers"


def test_owner_of_route_returns_none_when_unowned():
    registry = ModuleRegistry()
    registry.register(_descriptor("transfers", routes=("transfers.overview",)))
    assert registry.owner_of_route("nowhere.route") is None


def test_owner_of_route_flags_duplicates():
    registry = ModuleRegistry()
    registry.register(_descriptor("a", routes=("shared.route",)))
    registry.register(_descriptor("b", routes=("shared.route",)))
    assert registry.owner_of_route("shared.route") == "__DUPLICATE__"


def test_usable_modules_excludes_ones_with_unmet_health_requirements():
    registry = ModuleRegistry()
    registry.register(_descriptor(
        "pos", health_requirements=(HealthRequirement(check_name="database"),)
    ))
    registry.register(_descriptor("dashboard"))  # no health requirements

    healthy_report = HealthReport(
        overall_status=HealthStatus.HEALTHY,
        checks=(HealthCheckResult("database", HealthStatus.HEALTHY),),
        generated_at=T0,
    )
    unhealthy_report = HealthReport(
        overall_status=HealthStatus.UNHEALTHY,
        checks=(HealthCheckResult("database", HealthStatus.UNHEALTHY),),
        generated_at=T0,
    )

    assert {m.module_id for m in registry.usable_modules(healthy_report)} == {"pos", "dashboard"}
    assert {m.module_id for m in registry.usable_modules(unhealthy_report)} == {"dashboard"}
