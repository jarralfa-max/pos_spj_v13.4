from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
from frontend.desktop.shell.background.background_service_registry import BackgroundServiceRegistry
from frontend.desktop.shell.background.background_service_supervisor import BackgroundServiceSupervisor
from frontend.desktop.shell.shutdown.shutdown_step_result import ShutdownStepStatus
from frontend.desktop.shell.shutdown.steps.workers_shutdown_step import WorkersShutdownStep
from tests.unit.shell.background.conftest import RecordingService
from tests.unit.shell.shutdown.conftest import context  # noqa: F401 (fixture)


def _registry(*service_ids) -> BackgroundServiceRegistry:
    registry = BackgroundServiceRegistry()
    for service_id in service_ids:
        registry.register(BackgroundServiceDescriptor(service_id=service_id, display_name=service_id))
    return registry


def test_no_bound_services_is_ok(context):
    supervisor = BackgroundServiceSupervisor(registry=_registry("sync"))
    result = WorkersShutdownStep(supervisor).run(context)
    assert result.status is ShutdownStepStatus.OK


def test_stops_every_bound_service(context):
    registry = _registry("sync", "poller")
    supervisor = BackgroundServiceSupervisor(registry=registry)
    sync_service, poller_service = RecordingService(), RecordingService()
    supervisor.bind("sync", sync_service)
    supervisor.bind("poller", poller_service)
    supervisor.start_all()

    result = WorkersShutdownStep(supervisor).run(context)
    assert result.status is ShutdownStepStatus.OK
    assert sync_service.stop_calls == 1
    assert poller_service.stop_calls == 1


def test_a_service_that_fails_to_stop_cleanly_produces_a_warning_not_a_failure(context):
    registry = _registry("sync")
    supervisor = BackgroundServiceSupervisor(registry=registry)
    service = RecordingService()

    def raising_stop():
        raise RuntimeError("won't close")

    service.stop = raising_stop
    supervisor.bind("sync", service)
    supervisor.start("sync")

    result = WorkersShutdownStep(supervisor).run(context)
    assert result.status is ShutdownStepStatus.WARNING
    assert "sync" in result.message


def test_one_service_failing_to_stop_does_not_prevent_others_from_stopping(context):
    registry = _registry("sync", "poller")
    supervisor = BackgroundServiceSupervisor(registry=registry)
    broken, healthy = RecordingService(), RecordingService()

    def raising_stop():
        raise RuntimeError("won't close")

    broken.stop = raising_stop
    supervisor.bind("sync", broken)
    supervisor.bind("poller", healthy)
    supervisor.start_all()

    WorkersShutdownStep(supervisor).run(context)
    assert healthy.stop_calls == 1
