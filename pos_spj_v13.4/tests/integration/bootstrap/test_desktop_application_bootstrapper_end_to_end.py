"""One real, full-weight bootstrap run — the actual migration engine (181+
migrations) against a fresh on-disk SQLite file, not a mock. Slow (~20-30s)
by nature of what it exercises; the fast, isolated behavior of each step and
of the engine itself is covered in tests/unit/bootstrap/.
"""
from pathlib import Path

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.default_steps import default_bootstrap_steps
from backend.bootstrap.desktop_application_bootstrapper import DesktopApplicationBootstrapper
from backend.bootstrap.health.application_health_check_runner import ApplicationHealthCheckRunner
from backend.bootstrap.health.checks import default_health_checks
from backend.bootstrap.health.health_status import HealthStatus
from backend.security.provisioning.installation import ProvisioningStatus


def test_full_bootstrap_against_a_fresh_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(tmp_path / "app_data"))
    context = BootstrapContext(db_path=tmp_path / "spj.db")
    bootstrapper = DesktopApplicationBootstrapper(
        default_bootstrap_steps(),
        health_check_runner=ApplicationHealthCheckRunner(default_health_checks()),
    )

    result = bootstrapper.bootstrap(context)

    assert result.success is True
    assert result.final_state is BootstrapState.RUNNING
    assert result.exit_code == 0
    assert len(result.step_results) == 6
    assert all(r.success for r in result.step_results)

    assert context.app_paths is not None
    assert context.conn is not None
    assert context.installation_status is ProvisioningStatus.UNINITIALIZED

    assert result.health_report is not None
    assert result.health_report.overall_status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
    # database/schema/uuid_identity are the hard-security checks — must be
    # HEALTHY on a just-migrated database no matter what (disk space could
    # legitimately be DEGRADED on a constrained CI runner).
    by_name = {c.check_name: c for c in result.health_report.checks}
    assert by_name["database"].status is HealthStatus.HEALTHY
    assert by_name["schema"].status is HealthStatus.HEALTHY
    assert by_name["uuid_identity"].status is HealthStatus.HEALTHY


def test_bootstrapping_the_same_database_twice_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(tmp_path / "app_data"))
    db_path = tmp_path / "spj.db"

    first = DesktopApplicationBootstrapper(default_bootstrap_steps()).bootstrap(
        BootstrapContext(db_path=db_path)
    )
    assert first.success is True
    first.context.conn.close()

    second = DesktopApplicationBootstrapper(default_bootstrap_steps()).bootstrap(
        BootstrapContext(db_path=db_path)
    )
    assert second.success is True
    assert second.context.installation_status is ProvisioningStatus.UNINITIALIZED
