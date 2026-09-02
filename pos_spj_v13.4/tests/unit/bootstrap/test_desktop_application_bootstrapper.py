from pathlib import Path

import pytest

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.bootstrap.desktop_application_bootstrapper import DesktopApplicationBootstrapper
from backend.bootstrap.health.application_health_check_runner import ApplicationHealthCheckRunner
from backend.bootstrap.health.health_status import HealthCheckResult, HealthStatus


class FakeStep:
    def __init__(self, name, resulting_state, result_factory):
        self.name = name
        self.resulting_state = resulting_state
        self._result_factory = result_factory
        self.called_with = None

    def run(self, context):
        self.called_with = context
        return self._result_factory()


class RaisingStep:
    name = "raising_step"
    resulting_state = BootstrapState.ENVIRONMENT_VALIDATING

    def run(self, context):
        raise RuntimeError("kaboom")


class FakeHealthCheck:
    def __init__(self, name, status):
        self.name = name
        self._status = status

    def check(self, context):
        return HealthCheckResult(self.name, self._status, "")


def _context() -> BootstrapContext:
    return BootstrapContext(db_path=Path("unused.db"))


def test_all_steps_succeed_reaches_running_state():
    steps = [
        FakeStep("a", BootstrapState.ENVIRONMENT_VALIDATING, lambda: BootstrapStepResult.ok("a")),
        FakeStep("b", BootstrapState.PATHS_READY, lambda: BootstrapStepResult.ok("b")),
    ]
    bootstrapper = DesktopApplicationBootstrapper(steps)
    result = bootstrapper.bootstrap(_context())

    assert result.success is True
    assert result.exit_code == 0
    assert result.final_state is BootstrapState.RUNNING
    assert len(result.step_results) == 2


def test_fatal_step_stops_execution():
    steps = [
        FakeStep("a", BootstrapState.ENVIRONMENT_VALIDATING, lambda: BootstrapStepResult.ok("a")),
        FakeStep("b", BootstrapState.PATHS_READY, lambda: BootstrapStepResult.fatal(
            "b", BootstrapFailureReason.SCHEMA_INCOMPLETE, "boom",
        )),
        FakeStep("c", BootstrapState.DATABASE_CHECKING, lambda: BootstrapStepResult.ok("c")),
    ]
    bootstrapper = DesktopApplicationBootstrapper(steps)
    result = bootstrapper.bootstrap(_context())

    assert result.success is False
    assert result.exit_code == 1
    assert result.final_state is BootstrapState.FAILED
    assert len(result.step_results) == 2  # step "c" never ran
    assert steps[2].called_with is None


def test_degraded_step_does_not_stop_execution():
    steps = [
        FakeStep("a", BootstrapState.ENVIRONMENT_VALIDATING, lambda: BootstrapStepResult.degraded(
            "a", BootstrapFailureReason.WHATSAPP_UNAVAILABLE, "no whatsapp",
        )),
        FakeStep("b", BootstrapState.PATHS_READY, lambda: BootstrapStepResult.ok("b")),
    ]
    bootstrapper = DesktopApplicationBootstrapper(steps)
    result = bootstrapper.bootstrap(_context())

    assert result.success is True
    assert result.final_state is BootstrapState.RUNNING
    assert "WHATSAPP_UNAVAILABLE" in result.degraded_capabilities


def test_warning_step_does_not_stop_execution_and_is_collected():
    steps = [
        FakeStep("a", BootstrapState.ENVIRONMENT_VALIDATING, lambda: BootstrapStepResult.warning(
            "a", BootstrapFailureReason.BACKUP_OVERDUE, "backup overdue",
        )),
        FakeStep("b", BootstrapState.PATHS_READY, lambda: BootstrapStepResult.ok("b")),
    ]
    bootstrapper = DesktopApplicationBootstrapper(steps)
    result = bootstrapper.bootstrap(_context())

    assert result.success is True
    assert "backup overdue" in result.warnings


def test_unhandled_step_exception_is_treated_as_fatal():
    bootstrapper = DesktopApplicationBootstrapper([RaisingStep()])
    result = bootstrapper.bootstrap(_context())

    assert result.success is False
    assert result.final_state is BootstrapState.FAILED
    failed = result.failed_step()
    assert failed is not None
    assert failed.exception_type == "RuntimeError"
    assert "kaboom" in failed.technical_details


def test_step_durations_are_recorded():
    steps = [FakeStep("a", BootstrapState.ENVIRONMENT_VALIDATING, lambda: BootstrapStepResult.ok("a"))]
    bootstrapper = DesktopApplicationBootstrapper(steps)
    result = bootstrapper.bootstrap(_context())

    assert result.step_results[0].duration_ms >= 0.0
    assert result.duration_ms() >= 0.0


def test_context_is_threaded_through_every_step():
    context = _context()
    steps = [
        FakeStep("a", BootstrapState.ENVIRONMENT_VALIDATING, lambda: BootstrapStepResult.ok("a")),
        FakeStep("b", BootstrapState.PATHS_READY, lambda: BootstrapStepResult.ok("b")),
    ]
    DesktopApplicationBootstrapper(steps).bootstrap(context)

    assert steps[0].called_with is context
    assert steps[1].called_with is context


def test_no_steps_still_reaches_running():
    bootstrapper = DesktopApplicationBootstrapper([])
    result = bootstrapper.bootstrap(_context())
    assert result.success is True
    assert result.final_state is BootstrapState.RUNNING


def test_health_report_attached_when_runner_provided():
    checks = [FakeHealthCheck("db", HealthStatus.HEALTHY), FakeHealthCheck("disk", HealthStatus.DEGRADED)]
    bootstrapper = DesktopApplicationBootstrapper([], health_check_runner=ApplicationHealthCheckRunner(checks))
    result = bootstrapper.bootstrap(_context())

    assert result.health_report is not None
    assert result.health_report.overall_status is HealthStatus.DEGRADED


def test_health_report_none_when_no_runner_provided():
    bootstrapper = DesktopApplicationBootstrapper([])
    result = bootstrapper.bootstrap(_context())
    assert result.health_report is None
