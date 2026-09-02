from datetime import datetime, timezone

from backend.bootstrap.health.health_status import (
    HealthCheckResult,
    HealthReport,
    HealthStatus,
    is_at_least,
    worse_of,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_worse_of_unhealthy_beats_everything():
    assert worse_of(HealthStatus.UNHEALTHY, HealthStatus.HEALTHY) is HealthStatus.UNHEALTHY
    assert worse_of(HealthStatus.HEALTHY, HealthStatus.UNHEALTHY) is HealthStatus.UNHEALTHY


def test_worse_of_degraded_beats_unknown_and_healthy():
    assert worse_of(HealthStatus.DEGRADED, HealthStatus.UNKNOWN) is HealthStatus.DEGRADED
    assert worse_of(HealthStatus.DEGRADED, HealthStatus.HEALTHY) is HealthStatus.DEGRADED


def test_worse_of_unknown_beats_healthy():
    assert worse_of(HealthStatus.UNKNOWN, HealthStatus.HEALTHY) is HealthStatus.UNKNOWN


def test_worse_of_healthy_and_healthy_is_healthy():
    assert worse_of(HealthStatus.HEALTHY, HealthStatus.HEALTHY) is HealthStatus.HEALTHY


def test_is_healthy_true_only_for_healthy_overall():
    report = HealthReport(overall_status=HealthStatus.HEALTHY, checks=(), generated_at=T0)
    assert report.is_healthy() is True

    report = HealthReport(overall_status=HealthStatus.DEGRADED, checks=(), generated_at=T0)
    assert report.is_healthy() is False


def test_failing_checks_excludes_healthy_ones():
    checks = (
        HealthCheckResult("a", HealthStatus.HEALTHY),
        HealthCheckResult("b", HealthStatus.DEGRADED, "slow disk"),
        HealthCheckResult("c", HealthStatus.UNHEALTHY, "db down"),
    )
    report = HealthReport(overall_status=HealthStatus.UNHEALTHY, checks=checks, generated_at=T0)
    failing = report.failing_checks()
    assert {c.check_name for c in failing} == {"b", "c"}


def test_is_at_least_true_when_status_meets_minimum():
    assert is_at_least(HealthStatus.HEALTHY, HealthStatus.DEGRADED) is True
    assert is_at_least(HealthStatus.DEGRADED, HealthStatus.DEGRADED) is True


def test_is_at_least_false_when_status_below_minimum():
    assert is_at_least(HealthStatus.DEGRADED, HealthStatus.HEALTHY) is False
    assert is_at_least(HealthStatus.UNHEALTHY, HealthStatus.DEGRADED) is False


def test_is_at_least_unknown_ranks_between_degraded_and_healthy():
    assert is_at_least(HealthStatus.UNKNOWN, HealthStatus.DEGRADED) is True
    assert is_at_least(HealthStatus.UNKNOWN, HealthStatus.HEALTHY) is False
