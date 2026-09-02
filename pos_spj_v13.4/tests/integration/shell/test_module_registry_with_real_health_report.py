"""ModuleRegistry against a real HealthReport — not fakes. Runs the actual
SHELL-4 database bootstrap sequence and SHELL-3 health check runner against
a fresh SQLite file, then checks `usable_modules()` behaves correctly with
the real check names ("database", "schema", "uuid_identity", ...).
"""
from backend.bootstrap.health.application_health_check_runner import ApplicationHealthCheckRunner
from backend.bootstrap.health.checks import default_health_checks
from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
from frontend.desktop.shell.modules.health_requirement import HealthRequirement
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.module_registry import ModuleRegistry


def test_module_with_real_health_requirements_is_usable_on_a_healthy_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SPJ_APP_DATA_DIR", str(tmp_path / "app_data"))
    bootstrap_result = run_database_bootstrap_sequence(tmp_path / "spj.db")
    assert bootstrap_result.success is True

    # run_database_bootstrap_sequence's narrower step list doesn't run
    # ApplicationPathsStep, so app_paths isn't set yet — the disk_space/
    # secret_store checks need it.
    from backend.shared.app_paths import AppPaths

    bootstrap_result.context.app_paths = AppPaths.from_environment()

    health_report = ApplicationHealthCheckRunner(default_health_checks()).run(bootstrap_result.context)

    registry = ModuleRegistry()
    registry.register(ModuleDescriptor(
        module_id="pos", display_name="Punto de Venta",
        health_requirements=(
            HealthRequirement(check_name="database"),
            HealthRequirement(check_name="schema"),
            HealthRequirement(check_name="uuid_identity"),
        ),
    ))
    registry.register(ModuleDescriptor(module_id="dashboard", display_name="Inicio"))

    usable = {m.module_id for m in registry.usable_modules(health_report)}
    assert "dashboard" in usable
    assert "pos" in usable  # database/schema/uuid_identity are HEALTHY on a fresh migrated DB

    bootstrap_result.context.conn.close()
