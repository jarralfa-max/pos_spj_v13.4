"""SchemaCompatibilityStep — the database must not be NEWER than the binary.

After an update has migrated the database, putting the previous executable
back WITHOUT restoring the pre-update backup leaves a database with
migrations this binary does not know. The migration engine would skip them
and the application would run against a schema it was not written for.
This step stops the start with an explicit way out instead.

Runs after `DatabaseIntegrityStep` (needs `context.conn`) and before
`DatabaseMigrationStep`.
"""
from __future__ import annotations

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_severity import BootstrapFailureReason
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.bootstrap_step_result import BootstrapStepResult


def known_migration_versions() -> frozenset[str]:
    from migrations.engine import MIGRATIONS

    return frozenset(m.version for m in MIGRATIONS)


class SchemaCompatibilityStep:
    name = "schema_compatibility"
    resulting_state = BootstrapState.DATABASE_CHECKING

    def run(self, context: BootstrapContext) -> BootstrapStepResult:
        if context.conn is None:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.BOOTSTRAP_INVALID,
                "schema_compatibility ejecutado sin conexión (database_integrity va antes).")
        tracked = context.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if tracked is None:
            return BootstrapStepResult.ok(self.name, "Base sin migraciones previas.")
        applied = {str(row[0]) for row in context.conn.execute(
            "SELECT version FROM schema_migrations")}
        unknown = sorted(applied - known_migration_versions())
        if unknown:
            return BootstrapStepResult.fatal(
                self.name, BootstrapFailureReason.SCHEMA_NEWER_THAN_APPLICATION,
                "La base de datos fue actualizada por una versión más nueva de SPJ "
                f"(migraciones {', '.join(unknown[-5:])} desconocidas para esta versión). "
                "Instale esa versión o restaure el respaldo previo a la actualización "
                "(carpeta de respaldos, archivo «pre-update-…»).")
        return BootstrapStepResult.ok(self.name, "Esquema compatible con esta versión.")
