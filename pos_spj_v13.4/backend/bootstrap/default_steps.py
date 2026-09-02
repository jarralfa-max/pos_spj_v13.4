"""default_bootstrap_steps — SHELL-3.

The ordered step list this phase actually implements. Steps for
subsystems that don't exist yet (SingleInstanceStep, LoggingStep,
CrashHandlingStep, ConfigurationBootstrapStep, CompositionRootStep,
ThemeBootstrapStep, AuthenticationBootstrapStep, ApplicationShellStep,
BackgroundServicesStep, UpdateCoordinatorStep — §8) are intentionally not
here yet; each later phase appends its own step(s) to this list rather than
this module growing speculative stubs ahead of the code they'd wrap.
"""
from __future__ import annotations

from backend.bootstrap.bootstrap_step import BootstrapStep
from backend.bootstrap.steps.application_paths_step import ApplicationPathsStep
from backend.bootstrap.steps.database_integrity_step import DatabaseIntegrityStep
from backend.bootstrap.steps.database_migration_step import DatabaseMigrationStep
from backend.bootstrap.steps.environment_validation_step import EnvironmentValidationStep
from backend.bootstrap.steps.installation_state_step import InstallationStateStep
from backend.bootstrap.steps.schema_validation_step import SchemaValidationStep


def default_bootstrap_steps() -> list[BootstrapStep]:
    return [
        EnvironmentValidationStep(),
        ApplicationPathsStep(),
        DatabaseIntegrityStep(),
        DatabaseMigrationStep(),
        SchemaValidationStep(),
        InstallationStateStep(),
    ]
