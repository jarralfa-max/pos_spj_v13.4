from datetime import datetime, timezone

from backend.bootstrap.health.health_status import HealthCheckResult, HealthReport, HealthStatus
from frontend.desktop.shell.modules.health_requirement import HealthRequirement, ModuleHealthEvaluator

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _report(**statuses: HealthStatus) -> HealthReport:
    checks = tuple(HealthCheckResult(name, status) for name, status in statuses.items())
    return HealthReport(overall_status=HealthStatus.HEALTHY, checks=checks, generated_at=T0)


def test_no_requirements_always_satisfied():
    evaluator = ModuleHealthEvaluator()
    assert evaluator.is_satisfied((), _report()) is True


def test_satisfied_when_check_meets_minimum():
    evaluator = ModuleHealthEvaluator()
    requirements = (HealthRequirement(check_name="database", minimum_status=HealthStatus.HEALTHY),)
    assert evaluator.is_satisfied(requirements, _report(database=HealthStatus.HEALTHY)) is True


def test_unsatisfied_when_check_below_minimum():
    evaluator = ModuleHealthEvaluator()
    requirements = (HealthRequirement(check_name="database", minimum_status=HealthStatus.HEALTHY),)
    assert evaluator.is_satisfied(requirements, _report(database=HealthStatus.DEGRADED)) is False


def test_satisfied_when_degraded_tolerated_explicitly():
    evaluator = ModuleHealthEvaluator()
    requirements = (HealthRequirement(check_name="secret_store", minimum_status=HealthStatus.DEGRADED),)
    assert evaluator.is_satisfied(requirements, _report(secret_store=HealthStatus.DEGRADED)) is True


def test_unsatisfied_when_check_missing_from_report():
    evaluator = ModuleHealthEvaluator()
    requirements = (HealthRequirement(check_name="whatsapp"),)
    assert evaluator.is_satisfied(requirements, _report(database=HealthStatus.HEALTHY)) is False


def test_unmet_requirements_lists_every_failure():
    evaluator = ModuleHealthEvaluator()
    requirements = (
        HealthRequirement(check_name="database", minimum_status=HealthStatus.HEALTHY),
        HealthRequirement(check_name="schema", minimum_status=HealthStatus.HEALTHY),
    )
    report = _report(database=HealthStatus.UNHEALTHY, schema=HealthStatus.HEALTHY)
    unmet = evaluator.unmet_requirements(requirements, report)
    assert len(unmet) == 1
    assert unmet[0].requirement.check_name == "database"
    assert unmet[0].actual_status is HealthStatus.UNHEALTHY


def test_unmet_requirement_reports_none_when_check_absent():
    evaluator = ModuleHealthEvaluator()
    requirements = (HealthRequirement(check_name="whatsapp"),)
    unmet = evaluator.unmet_requirements(requirements, _report())
    assert unmet[0].actual_status is None


def test_multiple_requirements_all_must_pass():
    evaluator = ModuleHealthEvaluator()
    requirements = (
        HealthRequirement(check_name="database", minimum_status=HealthStatus.HEALTHY),
        HealthRequirement(check_name="secret_store", minimum_status=HealthStatus.HEALTHY),
    )
    report = _report(database=HealthStatus.HEALTHY, secret_store=HealthStatus.DEGRADED)
    assert evaluator.is_satisfied(requirements, report) is False
