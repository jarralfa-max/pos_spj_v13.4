"""ApplicationPathsStep — SHELL-3.

Resolves and creates `AppPaths.user_data_dir` and its subdirectories.
Everything downstream (DatabaseIntegrityStep, SecretStoreHealthCheck,
DiskSpaceHealthCheck) depends on `context.app_paths` being set.
"""
from __future__ import annotations

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult
from backend.shared.app_paths import AppPaths


class ApplicationPathsStep:
    name = "application_paths"
    resulting_state = BootstrapState.PATHS_READY

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        app_paths = AppPaths.from_environment()
        try:
            app_paths.ensure_directories()
        except OSError as exc:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.CRITICAL_CONFIGURATION_MISSING,
                f"No se pudieron crear los directorios de datos en {app_paths.user_data_dir}: {exc}",
                exception=exc,
            )
        context.app_paths = app_paths
        return BootstrapStepResult.ok(self.name, f"Directorio de datos: {app_paths.user_data_dir}")
