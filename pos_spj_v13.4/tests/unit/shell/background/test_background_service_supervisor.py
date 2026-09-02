import pytest

from backend.bootstrap.health.health_status import HealthStatus
from frontend.desktop.shell.background.background_service_state import BackgroundServiceState
from frontend.desktop.shell.background.background_service_supervisor import BackgroundServiceSupervisor
from frontend.desktop.shell.background.errors import ServiceInstanceNotBoundError
from frontend.desktop.shell.background.restart_policy import RestartPolicy


def _supervisor(registry, *, restart_policy=None, scheduler=None):
    kwargs = dict(registry=registry)
    if restart_policy is not None:
        kwargs["restart_policy"] = restart_policy
    if scheduler is not None:
        kwargs["scheduler"] = scheduler
    return BackgroundServiceSupervisor(**kwargs)


def test_unbound_service_state_is_not_started(registry):
    supervisor = _supervisor(registry)
    assert supervisor.state_of("sync") is BackgroundServiceState.NOT_STARTED


def test_start_without_binding_an_instance_raises(registry):
    supervisor = _supervisor(registry)
    with pytest.raises(ServiceInstanceNotBoundError):
        supervisor.start("sync")


def test_start_unregistered_service_id_raises(registry, service):
    from frontend.desktop.shell.background.errors import ServiceNotFoundError
    supervisor = _supervisor(registry)
    with pytest.raises(ServiceNotFoundError):
        supervisor.start("does_not_exist")


def test_successful_start_reaches_running_state(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING
    assert service.start_calls == 1


def test_status_of_running_service_has_started_at_and_no_error(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    status = supervisor.status_of("sync")
    assert status.started_at is not None
    assert status.last_error is None
    assert status.crashes == ()


def test_start_all_starts_every_bound_service(registry, service):
    from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
    registry.register(BackgroundServiceDescriptor(service_id="poller", display_name="Poller"))
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start_all()
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING
    assert supervisor.state_of("poller") is BackgroundServiceState.NOT_STARTED  # never bound


def test_stop_calls_the_instance_and_sets_stopped_state(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    supervisor.stop("sync")
    assert supervisor.state_of("sync") is BackgroundServiceState.STOPPED
    assert service.stop_calls == 1


def test_stop_on_a_never_started_service_is_safe(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.stop("sync")  # must not raise
    assert supervisor.state_of("sync") is BackgroundServiceState.STOPPED


def test_start_that_raises_synchronously_is_treated_as_a_crash(registry, service):
    # A deferred scheduler isolates a single crash — with the default
    # *synchronous* scheduler, a permanently-failing service would exhaust
    # its whole restart budget inside this one start() call (covered by
    # test_exhausting_restart_policy_marks_the_service_failed below).
    service.fail = True
    scheduled = []
    supervisor = _supervisor(
        registry, restart_policy=RestartPolicy(max_restarts=10),
        scheduler=lambda task, delay: scheduled.append((task, delay)),
    )
    supervisor.bind("sync", service)
    supervisor.start("sync")
    assert supervisor.state_of("sync") is BackgroundServiceState.RESTARTING
    assert len(supervisor.status_of("sync").crashes) == 1
    assert len(scheduled) == 1


def test_notify_crashed_schedules_a_restart_via_the_injected_scheduler(registry, service):
    scheduled = []
    supervisor = _supervisor(
        registry, restart_policy=RestartPolicy(max_restarts=10),
        scheduler=lambda task, delay: scheduled.append((task, delay)),
    )
    supervisor.bind("sync", service)
    supervisor.start("sync")
    supervisor.notify_crashed("sync", RuntimeError("boom"))
    assert supervisor.state_of("sync") is BackgroundServiceState.RESTARTING
    assert len(scheduled) == 1


def test_running_the_scheduled_restart_recovers_the_service(registry, service):
    scheduled = []
    supervisor = _supervisor(
        registry, restart_policy=RestartPolicy(max_restarts=10),
        scheduler=lambda task, delay: scheduled.append((task, delay)),
    )
    supervisor.bind("sync", service)
    supervisor.start("sync")
    supervisor.notify_crashed("sync", RuntimeError("boom"))
    scheduled[0][0]()
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING
    assert service.start_calls == 2


def test_restart_backoff_delay_grows_with_the_default_immediate_scheduler(registry, service):
    supervisor = _supervisor(registry, restart_policy=RestartPolicy(
        max_restarts=10, initial_backoff_seconds=1, backoff_multiplier=2, max_backoff_seconds=100,
    ))
    supervisor.bind("sync", service)
    supervisor.start("sync")
    # immediate_restart_scheduler runs the task synchronously, ignoring delay,
    # so notify_crashed() resolves straight through to a real retry attempt.
    supervisor.notify_crashed("sync", RuntimeError("boom"))
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING
    assert service.start_calls == 2


def test_exhausting_restart_policy_marks_the_service_failed(registry, service):
    service.fail = True
    supervisor = _supervisor(registry, restart_policy=RestartPolicy(max_restarts=2, window_seconds=3600))
    supervisor.bind("sync", service)
    supervisor.start("sync")  # crash 1 -> retries (immediate scheduler) -> crash 2 -> gives up
    assert supervisor.state_of("sync") is BackgroundServiceState.FAILED
    assert len(supervisor.status_of("sync").crashes) == 2


def test_manual_start_after_failure_resets_crash_history_and_can_recover(registry, service):
    service.fail = True
    supervisor = _supervisor(registry, restart_policy=RestartPolicy(max_restarts=2, window_seconds=3600))
    supervisor.bind("sync", service)
    supervisor.start("sync")
    assert supervisor.state_of("sync") is BackgroundServiceState.FAILED

    service.fail = False
    supervisor.start("sync")
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING
    assert supervisor.status_of("sync").crashes == ()


def test_stop_resets_crash_history(registry, service):
    service.fail = True
    supervisor = _supervisor(registry, restart_policy=RestartPolicy(max_restarts=2, window_seconds=3600))
    supervisor.bind("sync", service)
    supervisor.start("sync")
    assert len(supervisor.status_of("sync").crashes) > 0
    supervisor.stop("sync")
    assert supervisor.status_of("sync").crashes == ()


def test_health_report_is_healthy_when_all_bound_services_are_running(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    report = supervisor.health_report()
    assert report.overall_status is HealthStatus.HEALTHY
    assert len(report.checks) == 1


def test_health_report_excludes_not_started_services(registry):
    supervisor = _supervisor(registry)
    report = supervisor.health_report()
    assert report.checks == ()
    assert report.overall_status is HealthStatus.HEALTHY


def test_health_report_excludes_stopped_services(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    supervisor.stop("sync")
    report = supervisor.health_report()
    assert report.checks == ()


def test_health_report_is_unhealthy_when_a_service_has_permanently_failed(registry, service):
    service.fail = True
    supervisor = _supervisor(registry, restart_policy=RestartPolicy(max_restarts=1, window_seconds=3600))
    supervisor.bind("sync", service)
    supervisor.start("sync")
    report = supervisor.health_report()
    assert report.overall_status is HealthStatus.UNHEALTHY
    assert report.checks[0].check_name == "background_service.sync"
    assert "service failed to start" in report.checks[0].message


def test_health_report_is_degraded_mid_restart_cycle(registry, service):
    scheduled = []
    supervisor = _supervisor(
        registry, restart_policy=RestartPolicy(max_restarts=10),
        scheduler=lambda task, delay: scheduled.append((task, delay)),
    )
    supervisor.bind("sync", service)
    supervisor.start("sync")
    supervisor.notify_crashed("sync", RuntimeError("transient"))
    report = supervisor.health_report()
    assert report.overall_status is HealthStatus.DEGRADED


def test_stop_returns_none_when_instance_stops_cleanly(registry, service):
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    assert supervisor.stop("sync") is None


def test_stop_that_raises_is_caught_and_returned_not_propagated(registry, service):
    def raising_stop():
        raise RuntimeError("cannot close cleanly")

    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")
    service.stop = raising_stop

    error = supervisor.stop("sync")  # must not raise
    assert isinstance(error, RuntimeError)
    assert supervisor.state_of("sync") is BackgroundServiceState.STOPPED
    assert supervisor.status_of("sync").last_error is error


def test_stop_all_stops_every_bound_service_and_reports_per_service_errors(registry, service):
    from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor
    from tests.unit.shell.background.conftest import RecordingService

    registry.register(BackgroundServiceDescriptor(service_id="poller", display_name="Poller"))
    poller = RecordingService()

    def raising_stop():
        raise RuntimeError("poller won't close")

    poller.stop = raising_stop

    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.bind("poller", poller)
    supervisor.start_all()

    results = supervisor.stop_all()
    assert results["sync"] is None
    assert isinstance(results["poller"], RuntimeError)
    assert supervisor.state_of("sync") is BackgroundServiceState.STOPPED
    assert supervisor.state_of("poller") is BackgroundServiceState.STOPPED


def test_stop_all_skips_unbound_registered_services(registry, service):
    from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor

    registry.register(BackgroundServiceDescriptor(service_id="poller", display_name="Poller"))
    supervisor = _supervisor(registry)
    supervisor.bind("sync", service)
    supervisor.start("sync")

    results = supervisor.stop_all()
    assert set(results.keys()) == {"sync"}


def test_last_error_is_cleared_after_a_successful_start_following_a_crash(registry, service):
    service.fail = True
    supervisor = _supervisor(registry, restart_policy=RestartPolicy(max_restarts=1, window_seconds=3600))
    supervisor.bind("sync", service)
    supervisor.start("sync")
    assert supervisor.status_of("sync").last_error is not None

    service.fail = False
    supervisor.start("sync")
    assert supervisor.state_of("sync") is BackgroundServiceState.RUNNING
    assert supervisor.status_of("sync").last_error is None


def test_last_error_is_cleared_after_a_successful_automatic_restart(registry, service):
    scheduled = []
    supervisor = _supervisor(
        registry, restart_policy=RestartPolicy(max_restarts=10),
        scheduler=lambda task, delay: scheduled.append((task, delay)),
    )
    supervisor.bind("sync", service)
    supervisor.start("sync")
    supervisor.notify_crashed("sync", RuntimeError("transient"))
    assert supervisor.status_of("sync").last_error is not None

    scheduled[0][0]()  # run the scheduled retry — service recovers
    assert supervisor.status_of("sync").last_error is None
