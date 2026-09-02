"""run_database_bootstrap_sequence — SHELL-4 §6 "Secuencia única".

The single canonical entry point for taking a SQLite file from "on disk" to
"integrity-checked, migrated, schema-and-UUID-validated" — replacing the
three separate, overlapping call sites `main.py` used to have
(`_bootstrap_db`'s own `bootstrap_database()` call, an immediate *second*
unconditional call to that same `bootstrap_database()`, and a third,
differently-error-handled block that opened its own connection and called
`migrator.up`/`migrate_db`/`verificar_tablas`/`assert_uuid_identity`
directly — see the SHELL-0 audit, `docs/refactor/application_bootstrap_audit.md`).

Reuses the exact `DatabaseIntegrityStep` → `DatabaseMigrationStep` →
`SchemaValidationStep` → `InstallationStateStep` sequence from SHELL-3
(`default_bootstrap_steps()` runs the same steps plus environment/paths,
for the full future app-bootstrap case) — not a second, parallel
implementation of "run migrations." `EnvironmentValidationStep` and
`ApplicationPathsStep` are intentionally excluded here: `main.py` still
computes its own DB path outside `AppPaths` (a separate reconciliation for
a later phase), so running `ApplicationPathsStep` here would create a
second, unused data-directory scheme alongside the one `main.py` already
uses.

Critically: any FATAL step now actually stops the boot. The old third block
in `main.py` caught a bare `Exception` from the migration engine, logged
"continuando con repositorios como fallback", and let the app start anyway
on a possibly half-migrated schema — exactly what §9 forbids ("no convertir
una excepción de migración crítica en warning"). That silent continuation
does not exist in this path: `DesktopApplicationBootstrapper` stops at the
first FATAL result, full stop.
"""
from __future__ import annotations

from pathlib import Path

from backend.bootstrap.bootstrap_context import BootstrapContext
from backend.bootstrap.bootstrap_result import BootstrapResult
from backend.bootstrap.desktop_application_bootstrapper import DesktopApplicationBootstrapper
from backend.bootstrap.steps.database_integrity_step import DatabaseIntegrityStep
from backend.bootstrap.steps.database_migration_step import DatabaseMigrationStep
from backend.bootstrap.steps.installation_state_step import InstallationStateStep
from backend.bootstrap.steps.schema_validation_step import SchemaValidationStep


def database_bootstrap_steps() -> list:
    return [
        DatabaseIntegrityStep(),
        DatabaseMigrationStep(),
        SchemaValidationStep(),
        InstallationStateStep(),
    ]


def run_database_bootstrap_sequence(db_path: str | Path) -> BootstrapResult:
    """Run the canonical DB bootstrap sequence once.

    The returned `BootstrapResult.context.conn`, if not None, is a live
    connection the caller owns and must close before handing the same
    database file to a separate connection pool (e.g. `AppContainer`'s
    `core.db.connection` pool) — this function never closes it itself,
    since a caller inspecting a FATAL failure may still need it (e.g. to
    read `PRAGMA integrity_check` details) before deciding what to do next.
    """
    bootstrapper = DesktopApplicationBootstrapper(database_bootstrap_steps())
    return bootstrapper.bootstrap(BootstrapContext(db_path=Path(db_path)))
