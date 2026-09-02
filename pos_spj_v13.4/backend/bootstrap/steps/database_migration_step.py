"""DatabaseMigrationStep — SHELL-3.

Runs the one canonical migration engine (`migrations.engine.up`) against
`context.conn` — the same engine `scripts/bootstrap_db.py` uses. This step
does not attempt to fix `engine.up()`'s internal per-migration
try/except-and-log behavior (flagged in the SHELL-0 audit as a real risk);
hardening that sequence is SHELL-4's job ("Database bootstrap: secuencia
única"). What this step *does* guarantee is that it never runs the engine
twice and never silently continues if `context.conn` is missing.
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

        from migrations import engine as migration_engine

        try:
            migration_engine.up(context.conn)
        except Exception as exc:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.SCHEMA_INCOMPLETE,
                f"El motor de migraciones falló: {exc}", exception=exc,
            )
        return BootstrapStepResult.ok(self.name, "Migraciones aplicadas.")
