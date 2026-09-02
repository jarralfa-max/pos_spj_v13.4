import pytest

from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
from frontend.desktop.shell.background.background_service_registry import BackgroundServiceRegistry


class RecordingService:
    """A `BackgroundService` test double: records start()/stop() calls and
    raises on `start()` while `fail` is True."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.fail = False

    def start(self) -> None:
        self.start_calls += 1
        if self.fail:
            raise RuntimeError("service failed to start")

    def stop(self) -> None:
        self.stop_calls += 1


@pytest.fixture
def service() -> RecordingService:
    return RecordingService()


@pytest.fixture
def registry() -> BackgroundServiceRegistry:
    reg = BackgroundServiceRegistry()
    reg.register(BackgroundServiceDescriptor(service_id="sync", display_name="Sync Engine", module_id="inventory"))
    return reg
