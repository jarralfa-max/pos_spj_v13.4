"""DatabaseMigrationStep — SHELL-3.

Runs the canonical fail-fast migration engine once. Import, contract,
execution and commit failures are fatal schema errors and block later steps.
"""
from __future__ import annotations

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult


class DatabaseMigrationStep:
    name = "database_migration"
    resulting_state = BootstrapState.DATABASE_READY

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if context.conn is None:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                "database_migration ejecutado sin una conexión abierta "
                "(database_integrity debe ejecutarse antes).",
            )

        try:
            from migrations import engine as migration_engine

            migration_engine.up(context.conn)
        except Exception as exc:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.SCHEMA_INCOMPLETE,
                f"El motor de migraciones falló: {exc}", exception=exc,
            )
        return BootstrapStepResult.ok(self.name, "Migraciones aplicadas.")
