from pathlib import Path

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.health.application_health_check_runner import ApplicationHealthCheckRunner
from backend.bootstrap.health.health_status import HealthCheckResult, HealthStatus


class FakeCheck:
    def __init__(self, name, status):
        self.name = name
        self._status = status

    def check(self, context):
        return HealthCheckResult(self.name, self._status, f"{self.name} says {self._status.value}")


class RaisingCheck:
    name = "raising"

    def check(self, context):
        raise RuntimeError("check exploded")


def _context() -> BootstrapContext:
    return BootstrapContext(db_path=Path("unused.db"))


def test_all_healthy_checks_yield_healthy_overall():
    runner = ApplicationHealthCheckRunner([FakeCheck("a", HealthStatus.HEALTHY), FakeCheck("b", HealthStatus.HEALTHY)])
    report = runner.run(_context())
    assert report.overall_status is HealthStatus.HEALTHY
    assert len(report.checks) == 2


def test_worst_check_determines_overall_status():
    runner = ApplicationHealthCheckRunner([
        FakeCheck("a", HealthStatus.HEALTHY),
        FakeCheck("b", HealthStatus.DEGRADED),
        FakeCheck("c", HealthStatus.HEALTHY),
    ])
    report = runner.run(_context())
    assert report.overall_status is HealthStatus.DEGRADED


def test_raising_check_is_reported_as_unhealthy_not_propagated():
    runner = ApplicationHealthCheckRunner([FakeCheck("a", HealthStatus.HEALTHY), RaisingCheck()])
    report = runner.run(_context())  # must not raise
    assert report.overall_status is HealthStatus.UNHEALTHY
    raising_result = next(c for c in report.checks if c.check_name == "raising")
    assert "check exploded" in raising_result.message


def test_empty_check_list_is_healthy():
    runner = ApplicationHealthCheckRunner([])
    report = runner.run(_context())
    assert report.overall_status is HealthStatus.HEALTHY
    assert report.checks == ()


def test_generated_at_is_set():
    runner = ApplicationHealthCheckRunner([])
    report = runner.run(_context())
    assert report.generated_at is not None
